import { useState, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Badge } from '../ui/Badge';
import { Upload, X, Check, AlertTriangle, FileText } from 'lucide-react';
import { apiClient } from '../../lib/api-client';

interface Props {
  projectId: string;
  importType: 'drawings' | 'materials' | 'equipment';
  label: string;
  queryKey: string[];
  sampleColumns: string[];
}

export function CsvImport({ projectId, importType, label, queryKey, sampleColumns }: Props) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<{ imported: number; skipped: number; errors: string[] } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) setFile(f);
    setResult(null);
  };

  const handleImport = async () => {
    if (!file) return;
    setImporting(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const text = await file.text();
      const res = await apiClient.post(`/api/engineering/import-${importType}/${projectId}`, text, {
        headers: { 'Content-Type': 'text/csv' },
      });
      setResult(res.data);
      queryClient.invalidateQueries({ queryKey });
      queryClient.invalidateQueries({ queryKey: ['engineering-change-summary'] });
    } catch (err: any) {
      setResult({ imported: 0, skipped: 0, errors: [err.response?.data?.detail || err.message] });
    }
    setImporting(false);
    setFile(null);
    if (fileRef.current) fileRef.current.value = '';
  };

  const endpoint = `/api/engineering/import-${importType}/${projectId}`;

  return (
    <div>
      <button onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-md border border-slate-600 text-slate-300 hover:text-white hover:border-slate-500 hover:bg-slate-800 transition-colors">
        <Upload className="h-3.5 w-3.5" /> {open ? 'Cancel Import' : `Import ${label} CSV`}
      </button>

      {open && (
        <div className="mt-4 p-4 bg-slate-900/60 border border-slate-700 rounded-lg space-y-4">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold text-white flex items-center gap-2">
              <FileText className="h-4 w-4" /> Import {label} from CSV
            </h4>
            <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-white"><X className="h-4 w-4" /></button>
          </div>

          {/* Sample format */}
          <div className="text-xs text-slate-400 bg-slate-950/60 p-3 rounded overflow-x-auto">
            <p className="text-slate-500 mb-1">Expected columns:</p>
            <code className="text-emerald-400">{sampleColumns.join(', ')}</code>
          </div>

          {/* File picker */}
          <div className="flex items-center gap-3">
            <input ref={fileRef} type="file" accept=".csv" onChange={handleFile}
              className="block w-full text-sm text-slate-400 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-primary file:text-white hover:file:bg-primary-light file:cursor-pointer" />
            <button onClick={handleImport} disabled={!file || importing}
              className="inline-flex items-center justify-center px-4 py-2 rounded-lg text-xs font-medium bg-primary hover:bg-primary-light text-white transition-colors disabled:opacity-50 shrink-0">
              {importing ? 'Importing...' : 'Upload & Import'}
            </button>
          </div>

          {/* Result */}
          {result && (
            <div className={`p-3 rounded-lg text-sm ${result.errors.length > 0 ? 'bg-amber-950/40 border border-amber-800/50' : 'bg-emerald-950/40 border border-emerald-800/50'}`}>
              <div className="flex items-center gap-2 mb-1">
                {result.errors.length > 0 ? <AlertTriangle className="h-4 w-4 text-amber-400" /> : <Check className="h-4 w-4 text-emerald-400" />}
                <span className="font-semibold text-white">
                  Imported: <Badge variant="success">{result.imported}</Badge> | Skipped: <Badge variant="warning">{result.skipped}</Badge>
                </span>
              </div>
              {result.errors.length > 0 && (
                <div className="mt-2 space-y-0.5 max-h-32 overflow-y-auto">
                  {result.errors.map((e, i) => <p key={i} className="text-xs text-amber-300">{e}</p>)}
                </div>
              )}
            </div>
          )}

          {/* API endpoint info */}
          <p className="text-xs text-slate-600">POST {endpoint}</p>
        </div>
      )}
    </div>
  );
}
