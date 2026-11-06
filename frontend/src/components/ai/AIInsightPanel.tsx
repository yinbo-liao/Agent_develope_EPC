import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, useRef, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { apiClient } from '../../lib/api-client';
import { Brain, Sparkles, AlertTriangle, Calendar, FileText, Zap, RefreshCw, Loader2, ChevronDown, ChevronUp, Send, MessageSquare, Database, Cpu } from 'lucide-react';

interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  toolCalls?: Array<{ name: string; result_summary: string }>;
  timestamp: string;
}

const ANALYSIS_TYPES = [
  { key: 'schedule_risk', label: 'Schedule Risk', icon: Calendar, desc: 'Analyze critical path and predict delays' },
  { key: 'conflict_detection', label: 'Conflict Detection', icon: AlertTriangle, desc: 'Scan for cross-phase conflicts' },
  { key: 'gate_assessment', label: 'Gate Assessment', icon: Zap, desc: 'Evaluate stage gate readiness' },
  { key: 'weekly_report', label: 'Weekly Report', icon: FileText, desc: 'Generate narrative weekly report' },
];

const SUGGESTED_QUERIES = [
  "What's the current project KPI summary?",
  'Show me critical path activities at risk',
  'How many open NCRs are there?',
  'What is the material receipt rate?',
  'Show recent safety incidents',
  'What are the active conflicts?',
];

export function AIInsightPanel({ projectId }: { projectId: string }) {
  const [collapsed, setCollapsed] = useState(false);
  const [running, setRunning] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  const [chatInput, setChatInput] = useState('');
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  const { data: aiStatus } = useQuery({
    queryKey: ['ai-status'],
    queryFn: () => apiClient.get('/api/ai/status'),
    refetchInterval: 60000,
  });

  const { data: insights } = useQuery({
    queryKey: ['ai-insights', projectId],
    queryFn: () => apiClient.get(`/api/ai/insights/${projectId}`),
    refetchInterval: 30000,
  });

  // Gate assessment requires a concrete gate id; use the project's first gate.
  const { data: stageGates } = useQuery({
    queryKey: ['stage-gates', projectId],
    queryFn: () => apiClient.get(`/api/stagegate/${projectId}`),
    staleTime: 30000,
  });

  const status = aiStatus?.data || {};
  const insightData = insights?.data || {};

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [chatMessages]);

  const sendChat = async () => {
    const query = chatInput.trim();
    if (!query || chatLoading) return;
    setChatInput('');
    setChatMessages(prev => [...prev, { role: 'user', content: query, timestamp: new Date().toISOString() }]);
    setChatLoading(true);
    try {
      const res = await apiClient.post(`/api/ai/chat/${projectId}`, { query, session_id: sessionId });
      const data = res.data;
      if (data.session_id) setSessionId(data.session_id);
      setChatMessages(prev => [...prev, {
        role: 'assistant',
        content: data.response || 'No response generated',
        toolCalls: data.tool_calls || [],
        timestamp: new Date().toISOString(),
      }]);
    } catch {
      setChatMessages(prev => [...prev, { role: 'assistant', content: 'Sorry, I encountered an error. Please try again.', timestamp: new Date().toISOString() }]);
    }
    setChatLoading(false);
  };

  const runAnalysis = async (type: string) => {
    setRunning(type);
    setResult(null);
    try {
      const payload: { analysis_type: string; week_end?: string; gate_id?: string } = {
        analysis_type: type,
      };
      if (type === 'weekly_report') {
        payload.week_end = new Date().toISOString().slice(0, 10);
      }
      if (type === 'gate_assessment') {
        const gates = Array.isArray(stageGates?.data) ? stageGates.data : [];
        const gateId = gates[0]?.gate_id;
        if (!gateId) {
          setResult({
            type,
            error: 'No stage gates are available to assess for this project.',
          });
          return;
        }
        payload.gate_id = gateId;
      }
      const res = await apiClient.post(`/api/ai/analyze/${projectId}`, payload);
      setResult({ type, data: res.data });
      queryClient.invalidateQueries({ queryKey: ['ai-insights'] });
      queryClient.invalidateQueries({ queryKey: ['stage-gates'] });
    } catch {
      setResult({ type, error: 'Analysis failed' });
    } finally {
      setRunning(null);
    }
  };

  if (collapsed) {
    return (
      <button
        onClick={() => setCollapsed(false)}
        className="fixed right-4 bottom-4 z-50 bg-slate-800 border border-slate-700 rounded-full p-3 shadow-lg hover:bg-slate-700 transition-colors"
        title="Open AI Panel"
      >
        <Brain className="h-5 w-5 text-purple-400" />
      </button>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Brain className="h-5 w-5 text-purple-400" />
          <h3 className="text-lg font-semibold text-white">AI Insights</h3>
        </div>
        <button onClick={() => setCollapsed(true)} className="p-1 text-slate-500 hover:text-white">
          <ChevronDown className="h-4 w-4" />
        </button>
      </div>

      {/* AI Status */}
      <Card className="border-l-4 border-l-purple-500">
        <CardContent className="py-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-purple-400" />
                <span className="text-sm font-semibold text-white">AI Engine</span>
                <Badge variant={status.enabled ? 'success' : 'default'}>
                  {status.enabled ? 'Claude Enabled' : 'Rule-Based'}
                </Badge>
              </div>
              <p className="text-[10px] text-slate-500 mt-0.5">
                {status.enabled
                  ? `Model: ${status.model} | Features: ${(status.features || []).length} agents`
                  : 'AI disabled — using rule-based fallbacks. Set FPSO_AI_ENABLED=true and provide FPSO_ANTHROPIC_API_KEY to enable.'}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Analysis Buttons */}
      <div className="grid gap-2">
        {ANALYSIS_TYPES.map(at => {
          const Icon = at.icon;
          const isRunning = running === at.key;
          return (
            <Card key={at.key}>
              <CardContent className="py-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Icon className="h-4 w-4 text-slate-400" />
                    <div>
                      <p className="text-sm font-medium text-white">{at.label}</p>
                      <p className="text-[10px] text-slate-500">{at.desc}</p>
                    </div>
                  </div>
                  <Button
                    onClick={() => runAnalysis(at.key)}
                    disabled={isRunning}
                    className="text-xs px-3 py-1.5"
                  >
                    {isRunning ? (
                      <><Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> Running</>
                    ) : (
                      <><RefreshCw className="h-3.5 w-3.5 mr-1" /> Analyze</>
                    )}
                  </Button>
                </div>
                {/* Result Display */}
                {result && result.type === at.key && (
                  <div className={`mt-3 p-3 rounded-lg ${result.error ? 'bg-red-500/10 border border-red-500/30' : 'bg-slate-800/50 border border-slate-700'}`}>
                    {result.error ? (
                      <p className="text-xs text-red-400">{result.error}</p>
                    ) : at.key === 'schedule_risk' ? (
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <Badge variant={result.data.risk_level === 'HIGH' ? 'destructive' : 'warning'}>{result.data.risk_level} Risk</Badge>
                          <span className="text-[10px] text-slate-500">via {result.data.generated_by || 'AI'}</span>
                        </div>
                        <p className="text-xs text-slate-300">{result.data.critical_path_health}</p>
                        {result.data.recommendations?.slice(0, 2).map((r: string, i: number) => (
                          <p key={i} className="text-[10px] text-slate-400 mt-0.5">• {r}</p>
                        ))}
                      </div>
                    ) : at.key === 'conflict_detection' ? (
                      <div>
                        <p className="text-xs text-slate-300">
                          {result.data.conflicts_found || 0} potential conflicts detected
                        </p>
                        {result.data.conflicts?.slice(0, 3).map((c: any, i: number) => (
                          <p key={i} className="text-[10px] text-slate-400 mt-0.5">• {c.title || c.conflict_type}</p>
                        ))}
                      </div>
                    ) : at.key === 'gate_assessment' ? (
                      <div>
                        <p className="text-xs text-white font-bold">
                          Score: {result.data.ai_readiness_score}/10 — {result.data.recommendation}
                        </p>
                      </div>
                    ) : at.key === 'weekly_report' ? (
                      <div className="max-h-40 overflow-y-auto">
                        <pre className="text-[10px] text-slate-300 whitespace-pre-wrap font-sans">{result.data.report?.slice(0, 500)}</pre>
                      </div>
                    ) : null}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Previous Insights Summary */}
      {(insightData?.ai_detected_conflicts?.length > 0 || insightData?.gate_readiness_scores?.length > 0) && (
        <Card>
          <CardHeader><CardTitle className="text-sm">Previous AI Findings</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-2 text-xs">
              {insightData.ai_detected_conflicts?.length > 0 && (
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
                  <span className="text-slate-400">
                    {insightData.ai_detected_conflicts.length} AI-detected conflicts
                  </span>
                </div>
              )}
              {insightData.gate_readiness_scores?.map((g: any) => (
                <div key={g.gate_name} className="flex items-center gap-2">
                  <Zap className="h-3.5 w-3.5 text-purple-400" />
                  <span className="text-slate-400">{g.gate_name}</span>
                  <span className="font-bold text-white">{g.ai_readiness_score}/10</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* RAG Chat Interface */}
      <Card className="border-l-4 border-l-purple-400">
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2">
            <MessageSquare className="h-4 w-4 text-purple-400" />
            Ask AI Assistant
            <Badge variant="outline" className="text-[10px] ml-auto">RAG + Tools</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {/* Chat Messages */}
          {chatMessages.length > 0 && (
            <div className="max-h-64 overflow-y-auto mb-3 space-y-2">
              {chatMessages.map((msg, i) => (
                <div key={i} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                  <div className={`max-w-[85%] rounded-lg px-3 py-2 text-xs ${
                    msg.role === 'user'
                      ? 'bg-purple-600/30 text-white'
                      : 'bg-slate-800 text-slate-300'
                  }`}>
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                    {msg.toolCalls && msg.toolCalls.length > 0 && (
                      <div className="mt-1.5 pt-1.5 border-t border-slate-700/50">
                        {msg.toolCalls.map((tc, j) => (
                          <div key={j} className="flex items-center gap-1 text-[10px] text-slate-500">
                            <Database className="h-3 w-3" />
                            <span>{tc.name}</span>
                            <span>—</span>
                            <span>{tc.result_summary || 'Complete'}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {chatLoading && (
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Thinking...
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
          )}

          {/* Suggested Queries */}
          {chatMessages.length === 0 && (
            <div className="mb-3">
              <p className="text-[10px] text-slate-500 mb-2">Try asking about:</p>
              <div className="flex flex-wrap gap-1.5">
                {SUGGESTED_QUERIES.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => { setChatInput(q); }}
                    className="text-[10px] px-2 py-1 rounded-full bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Chat Input */}
          <div className="flex gap-2">
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); } }}
              placeholder="Ask about project data..."
              className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500"
            />
            <Button
              onClick={sendChat}
              disabled={chatLoading || !chatInput.trim()}
              className="px-3 py-2 text-xs"
            >
              {chatLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
            </Button>
          </div>
          {sessionId && (
            <p className="text-[10px] text-slate-600 mt-1.5">Session active — conversation context preserved</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
