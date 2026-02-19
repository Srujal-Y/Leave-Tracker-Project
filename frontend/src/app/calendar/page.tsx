"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, Loader2, Plus, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";

import { AppShell } from "@/components/app-shell";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch } from "@/lib/api";
import { getAccessToken, getAuthUser, isAdmin } from "@/lib/auth";

type CalendarEntry = {
  id: number;
  employee_name: string;
  leave_type: string;
  start_date: string;
  end_date: string;
};

type CalendarCell = {
  day: number | null;
  entries: CalendarEntry[];
};

type Holiday = {
  id: number;
  date: string;
  name: string;
};

type WeekEntry = {
  day: string;
  entries: CalendarEntry[];
};

type CalendarPayload = {
  mode: "month" | "week";
  anchor: string;
  prev_month: string;
  next_month: string;
  calendar_rows: CalendarCell[][];
  selected_date: string | null;
  selected_entries: CalendarEntry[];
  week_anchor: string;
  week_entries: WeekEntry[];
  holidays: Holiday[];
};

const weekdayLabels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function toIsoDate(yearMonth: string, day: number) {
  const [year, month] = yearMonth.split("-").map((value) => Number(value));
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.toISOString().slice(0, 10);
}

export default function CalendarPage() {
  const router = useRouter();
  const user = getAuthUser();
  const adminUser = isAdmin(user);
  const [mode, setMode] = useState<"month" | "week">("month");
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [weekDate, setWeekDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [selectedDate, setSelectedDate] = useState("");
  const [calendar, setCalendar] = useState<CalendarPayload | null>(null);
  const [loading, setLoading] = useState(true);

  const [holidayDate, setHolidayDate] = useState("");
  const [holidayName, setHolidayName] = useState("");
  const [holidaySaving, setHolidaySaving] = useState(false);
  const [icsFile, setIcsFile] = useState<File | null>(null);
  const [icsImporting, setIcsImporting] = useState(false);

  const monthLabel = useMemo(() => {
    const anchor = calendar?.anchor ? new Date(`${calendar.anchor}T00:00:00`) : new Date(`${month}-01T00:00:00`);
    return anchor.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  }, [calendar?.anchor, month]);

  const weekLabel = useMemo(() => {
    const entries = calendar?.week_entries || [];
    if (entries.length) {
      const first = new Date(`${entries[0].day}T00:00:00`);
      const last = new Date(`${entries[entries.length - 1].day}T00:00:00`);
      const sameYear = first.getFullYear() === last.getFullYear();
      const firstText = first.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        ...(sameYear ? {} : { year: "numeric" }),
      });
      const lastText = last.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
      return `${firstText} - ${lastText}`;
    }
    const anchor = new Date(`${weekDate}T00:00:00`);
    return anchor.toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" });
  }, [calendar?.week_entries, weekDate]);

  const query = useMemo(() => {
    const params = new URLSearchParams();
    params.set("mode", mode);
    params.set("month", month);
    if (selectedDate) params.set("day", selectedDate);
    if (weekDate) params.set("week_date", weekDate);
    return params.toString();
  }, [mode, month, selectedDate, weekDate]);

  async function loadCalendar() {
    setLoading(true);
    try {
      const response = await apiFetch(`/leave/calendar/?${query}`);
      if (!response.ok) throw new Error("Failed to load calendar");
      const payload = (await response.json()) as CalendarPayload;
      setCalendar(payload);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to load calendar");
    } finally {
      setLoading(false);
    }
  }

  async function addHoliday() {
    if (!holidayDate || !holidayName.trim()) return;
    setHolidaySaving(true);
    try {
      const response = await apiFetch("/leave/holidays/", {
        method: "POST",
        body: JSON.stringify({ date: holidayDate, name: holidayName.trim() }),
      });
      if (!response.ok) {
        const payload = await response.json();
        throw new Error(payload.detail || "Could not add holiday");
      }
      toast.success("Holiday added");
      setHolidayDate("");
      setHolidayName("");
      void loadCalendar();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not add holiday");
    } finally {
      setHolidaySaving(false);
    }
  }

  async function deleteHoliday(id: number) {
    try {
      const response = await apiFetch(`/leave/holidays/${id}/`, { method: "DELETE" });
      if (!response.ok && response.status !== 204) {
        throw new Error("Could not delete holiday");
      }
      toast.success("Holiday deleted");
      void loadCalendar();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not delete holiday");
    }
  }

  async function importHolidaysFromIcs() {
    if (!icsFile) return;
    setIcsImporting(true);
    try {
      const formData = new FormData();
      formData.append("file", icsFile);
      const response = await apiFetch("/leave/holidays/import-ics/", {
        method: "POST",
        body: formData,
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Could not import .ics file");
      }
      toast.success(
        `Imported holidays: ${payload.created || 0} created, ${payload.updated || 0} updated, ${payload.unchanged || 0} unchanged.`,
      );
      setIcsFile(null);
      void loadCalendar();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not import .ics file");
    } finally {
      setIcsImporting(false);
    }
  }

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    void loadCalendar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, query]);

  return (
    <AppShell>
      <PageHeader
        title="Calendar"
        description="Track who is out by day or week, and manage public holidays."
        badge={<Badge variant="outline">Planner</Badge>}
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="surface-card lg:col-span-2">
          <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle>Team Calendar</CardTitle>
              <p className="mt-1 text-sm font-medium text-foreground/90">{mode === "month" ? monthLabel : weekLabel}</p>
            </div>
            <div className="flex items-center gap-2">
              <Select value={mode} onValueChange={(value: "month" | "week") => setMode(value)}>
                <SelectTrigger className="w-[130px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="month">Month</SelectItem>
                  <SelectItem value="week">Week</SelectItem>
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                size="icon"
                onClick={() => {
                  if (mode === "month" && calendar?.prev_month) setMonth(calendar.prev_month);
                  if (mode === "week") {
                    const d = new Date(`${weekDate}T00:00:00`);
                    d.setDate(d.getDate() - 7);
                    setWeekDate(d.toISOString().slice(0, 10));
                  }
                }}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                onClick={() => {
                  if (mode === "month" && calendar?.next_month) setMonth(calendar.next_month);
                  if (mode === "week") {
                    const d = new Date(`${weekDate}T00:00:00`);
                    d.setDate(d.getDate() + 7);
                    setWeekDate(d.toISOString().slice(0, 10));
                  }
                }}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {loading ? (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading calendar...
              </div>
            ) : mode === "month" ? (
              <div className="space-y-2 rounded-xl border border-border/60 bg-card/50 p-3">
                <div className="grid grid-cols-7 gap-2">
                  {weekdayLabels.map((label) => (
                    <div key={label} className="rounded-md border border-border/60 bg-muted/40 px-2 py-1 text-center text-xs font-medium">
                      {label}
                    </div>
                  ))}
                </div>
                {(calendar?.calendar_rows || []).map((week, weekIndex) => (
                  <div className="grid grid-cols-7 gap-2" key={weekIndex}>
                    {week.map((cell, cellIndex) => (
                      <button
                        key={`${weekIndex}-${cellIndex}`}
                        type="button"
                        disabled={!cell.day}
                        onClick={() => {
                          if (!cell.day) return;
                          setSelectedDate(toIsoDate(month, cell.day));
                        }}
                        className="min-h-24 rounded-md border border-border/60 bg-card/80 p-2 text-left transition hover:border-primary/60 disabled:cursor-default disabled:opacity-40"
                      >
                        <div className="text-xs font-medium">{cell.day || "-"}</div>
                        {cell.entries.length ? (
                          <div className="mt-2 space-y-1">
                            {cell.entries.slice(0, 2).map((entry) => (
                              <div className="rounded bg-primary/15 px-1 py-0.5 text-[11px]" key={entry.id}>
                                {entry.employee_name}
                              </div>
                            ))}
                            {cell.entries.length > 2 ? (
                              <div className="text-[10px] text-muted-foreground">+{cell.entries.length - 2} more</div>
                            ) : null}
                          </div>
                        ) : null}
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            ) : (
              <div className="grid gap-2 rounded-xl border border-border/60 bg-card/50 p-3 md:grid-cols-2">
                {(calendar?.week_entries || []).map((item) => (
                  <Card key={item.day} className="surface-card">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">{item.day}</CardTitle>
                    </CardHeader>
                    <CardContent>
                      {item.entries.length ? (
                        <div className="space-y-1">
                          {item.entries.map((entry) => (
                            <div key={entry.id} className="rounded bg-primary/10 px-2 py-1 text-xs">
                              {entry.employee_name} - {entry.leave_type}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-muted-foreground">No one is off.</p>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}

            {calendar?.selected_entries?.length ? (
              <div className="soft-panel">
                <p className="mb-2 text-sm font-medium">Selected day: {calendar.selected_date}</p>
                <div className="space-y-2">
                  {calendar.selected_entries.map((entry) => (
                    <div className="rounded bg-muted/30 p-2 text-sm" key={entry.id}>
                      <span className="font-medium">{entry.employee_name}</span> - {entry.leave_type} ({entry.start_date} to {entry.end_date})
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card className="surface-card">
          <CardHeader>
            <CardTitle>Public Holidays</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {(calendar?.holidays || []).length ? (
              <Table className="[&_th]:h-10 [&_th]:text-xs [&_th]:uppercase [&_th]:tracking-wide">
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Name</TableHead>
                    {adminUser ? <TableHead className="text-right">Action</TableHead> : null}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(calendar?.holidays || []).map((holiday) => (
                    <TableRow key={holiday.id}>
                      <TableCell>{holiday.date}</TableCell>
                      <TableCell>{holiday.name}</TableCell>
                      {adminUser ? (
                        <TableCell className="text-right">
                          <Button variant="ghost" size="icon" onClick={() => deleteHoliday(holiday.id)}>
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </TableCell>
                      ) : null}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <p className="text-sm text-muted-foreground">No holidays configured for this month.</p>
            )}

            {adminUser ? (
              <div className="soft-panel space-y-3">
                <Badge variant="secondary">Admin</Badge>
                <div className="space-y-1">
                  <Label htmlFor="holiday-date">Date</Label>
                  <Input
                    id="holiday-date"
                    type="date"
                    value={holidayDate}
                    onChange={(event) => setHolidayDate(event.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="holiday-name">Holiday Name</Label>
                  <Input
                    id="holiday-name"
                    value={holidayName}
                    onChange={(event) => setHolidayName(event.target.value)}
                    placeholder="Ex: Founders Day"
                  />
                </div>
                <Button onClick={addHoliday} disabled={holidaySaving} className="w-full">
                  {holidaySaving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-4 w-4" />}
                  Add Holiday
                </Button>
                <div className="border-t border-border/60 pt-3">
                  <Label htmlFor="holiday-ics" className="mb-1 block">
                    Import Google Calendar .ics
                  </Label>
                  <Input
                    id="holiday-ics"
                    type="file"
                    accept=".ics,text/calendar"
                    onChange={(event) => setIcsFile(event.target.files?.[0] || null)}
                  />
                  <Button onClick={importHolidaysFromIcs} disabled={icsImporting || !icsFile} className="mt-2 w-full" variant="outline">
                    {icsImporting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
                    Import ICS Holidays
                  </Button>
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
