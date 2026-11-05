import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Progress } from '../ui/Progress';
import { apiClient } from '../../lib/api-client';
import { GraduationCap, AlertTriangle, CheckCircle, Clock, XCircle } from 'lucide-react';

const STATUS_STYLES: Record<string, string> = {
  VALID: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
  EXPIRING: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  EXPIRED: 'bg-red-500/10 text-red-400 border-red-500/30',
  MISSING: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
};

export function TrainingMatrix({ projectId }: { projectId: string }) {
  const { data: matrix, isLoading } = useQuery({
    queryKey: ['training-matrix', projectId],
    queryFn: () => apiClient.get(`/api/training/matrix/${projectId}`),
    refetchInterval: 60000,
  });

  const { data: expiring } = useQuery({
    queryKey: ['expiring-certs', projectId],
    queryFn: () => apiClient.get(`/api/training/expiring-certifications/${projectId}?days_ahead=30`),
    refetchInterval: 60000,
  });

  const matrixData = matrix?.data || [];
  const expiringList = expiring?.data || [];

  // Pivot matrix data: rows = roles, columns = courses
  const roles = [...new Set<string>(matrixData.map((m: any) => m.role_name))];
  const courses = [...new Set<string>(matrixData.map((m: any) => m.course_name))];

  const getCell = (role: string, course: string) =>
    matrixData.find((m: any) => m.role_name === role && m.course_name === course);

  // Overall compliance
  const allCompliance = matrixData.map((m: any) => m.compliance_pct || 0);
  const avgCompliance = allCompliance.length > 0
    ? Math.round(allCompliance.reduce((a: number, b: number) => a + b, 0) / allCompliance.length)
    : 0;

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <GraduationCap className="h-5 w-5 text-blue-400" />
        <h3 className="text-lg font-semibold text-white">Training Compliance Matrix</h3>
      </div>

      {/* Overall Compliance KPI */}
      <div className="grid gap-3 sm:grid-cols-3">
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">Overall Compliance</p>
            <p className={`text-2xl font-bold ${avgCompliance >= 80 ? 'text-emerald-400' : avgCompliance >= 60 ? 'text-amber-400' : 'text-red-400'}`}>
              {avgCompliance}%
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">Roles Tracked</p>
            <p className="text-2xl font-bold text-blue-400">{roles.length}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">Expiring (30 days)</p>
            <p className={`text-2xl font-bold ${expiringList.length > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
              {expiringList.length}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Matrix Table */}
      {isLoading ? (
        <div className="text-center py-10 text-slate-500">Loading training data...</div>
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto max-h-96 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-slate-900">
                  <tr className="text-slate-500 border-b border-slate-800">
                    <th className="text-left py-2 px-3 font-medium sticky left-0 bg-slate-900 z-10">Role</th>
                    {courses.map((course: string) => (
                      <th key={course} className="text-center py-2 px-3 font-medium max-w-[120px]">
                        <div className="truncate" title={course}>{course}</div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {roles.map((role: string) => (
                    <tr key={role} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                      <td className="py-2 px-3 font-semibold text-slate-300 sticky left-0 bg-slate-900/95 z-10">
                        {role}
                      </td>
                      {courses.map((course: string) => {
                        const cell = getCell(role, course);
                        const pct = cell?.compliance_pct || 0;
                        const total = cell?.total_personnel || 0;
                        const certified = cell?.certified_count || 0;

                        let statusStyle = STATUS_STYLES.MISSING;
                        if (pct >= 90) statusStyle = STATUS_STYLES.VALID;
                        else if (pct >= 50) statusStyle = STATUS_STYLES.EXPIRING;
                        else if (total > 0) statusStyle = STATUS_STYLES.EXPIRED;

                        return (
                          <td key={course} className="py-2 px-2 text-center">
                            {cell ? (
                              <div className={`px-2 py-1 rounded border ${statusStyle}`}>
                                <p className="font-bold text-[11px]">{pct}%</p>
                                <p className="text-[9px] opacity-70">{certified}/{total}</p>
                              </div>
                            ) : (
                              <span className="text-slate-600">—</span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Expiring Certifications */}
      {expiringList.length > 0 && (
        <Card className="border-l-4 border-l-amber-500">
          <CardHeader>
            <CardTitle className="text-sm text-amber-400 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4" />
              Expiring Certifications (within 30 days)
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto max-h-64 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-slate-900">
                  <tr className="text-slate-500 border-b border-slate-800">
                    <th className="text-left py-2 px-3 font-medium">Personnel</th>
                    <th className="text-left py-2 px-3 font-medium">Badge #</th>
                    <th className="text-left py-2 px-3 font-medium">Discipline</th>
                    <th className="text-left py-2 px-3 font-medium">Company</th>
                    <th className="text-left py-2 px-3 font-medium">Course</th>
                    <th className="text-left py-2 px-3 font-medium">Cert Ref</th>
                    <th className="text-center py-2 px-3 font-medium">Expiry Date</th>
                    <th className="text-center py-2 px-3 font-medium">Days Left</th>
                  </tr>
                </thead>
                <tbody>
                  {expiringList.map((e: any, idx: number) => (
                    <tr key={idx} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                      <td className="py-2 px-3 text-slate-300">{e.full_name}</td>
                      <td className="py-2 px-3 font-mono text-slate-400">{e.badge_number}</td>
                      <td className="py-2 px-3 text-slate-400">{e.discipline || '—'}</td>
                      <td className="py-2 px-3 text-slate-400">{e.contractor_company || '—'}</td>
                      <td className="py-2 px-3 text-slate-300">{e.course_name}</td>
                      <td className="py-2 px-3 font-mono text-slate-400">{e.certificate_ref || '—'}</td>
                      <td className="py-2 px-3 text-center text-slate-300">{e.expiry_date}</td>
                      <td className="py-2 px-3 text-center">
                        <Badge variant={e.days_remaining <= 7 ? 'destructive' : 'warning'}>
                          {e.days_remaining}d
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
