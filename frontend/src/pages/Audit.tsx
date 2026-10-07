import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAudit } from "@/lib/hooks";
import { EmptyState, SectionLabel, SiteSwitch, fmtTime } from "@/lib/ui";

export default function Audit() {
  const [filter, setFilter] = useState("all");
  const { data, isLoading } = useAudit(filter === "all" ? undefined : filter);

  return (
    <div className="space-y-5">
      <div>
        <SectionLabel>Immutable Editorial Audit Log</SectionLabel>
        <h1 className="page-title">Decision & Action Trail</h1>
        <p className="page-lede">Every automated decision, gate verification, and human action — with secrets redacted.</p>
      </div>

      <SiteSwitch value={filter} onChange={setFilter} testidPrefix="audit-filter" />

      <Card className="border-slate-200 surface p-0">
        {isLoading ? (
          <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-slate-500" /></div>
        ) : !data || data.length === 0 ? (
          <div className="p-6"><EmptyState title="No audit entries yet" hint="Actions across the pipeline appear here." /></div>
        ) : (
          <Table data-testid="audit-log-table">
            <TableHeader>
              <TableRow className="border-slate-200 hover:bg-transparent">
                <TableHead className="w-40">Time</TableHead>
                <TableHead>Action</TableHead>
                <TableHead className="w-28">Actor</TableHead>
                <TableHead className="w-28">Site</TableHead>
                <TableHead>Detail</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((e) => (
                <TableRow key={e.id} className="border-slate-200/60" data-testid={`audit-row-${e.id}`}>
                  <TableCell className="font-mono text-xs text-slate-500">{fmtTime(e.at)}</TableCell>
                  <TableCell className="font-mono text-xs text-sky-700">{e.action}</TableCell>
                  <TableCell className="text-xs text-slate-600">{e.actor}</TableCell>
                  <TableCell className="text-xs text-slate-600">{e.site_key ?? "—"}</TableCell>
                  <TableCell className="max-w-md truncate font-mono text-[11px] text-slate-500">
                    {e.detail ? JSON.stringify(e.detail) : "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>
    </div>
  );
}
