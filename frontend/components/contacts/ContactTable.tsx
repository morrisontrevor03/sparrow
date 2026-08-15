"use client";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Copy, ExternalLink, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { contacts as contactsApi, type Contact } from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUSES = [
  { value: "discovered", label: "Discovered" },
  { value: "message_drafted", label: "Drafted" },
  { value: "sent", label: "Sent" },
  { value: "replied", label: "Replied" },
  { value: "meeting_scheduled", label: "Meeting" },
];

function fullName(c: Contact) {
  return `${c.first_name ?? ""} ${c.last_name ?? ""}`.trim() || "Unknown";
}

function ScoreDot({ score }: { score: number | null }) {
  const value = score ?? 0;
  return (
    <span
      title={`Relevance ${(value * 100).toFixed(0)}%`}
      className={cn(
        "inline-block h-2 w-2 shrink-0 rounded-full",
        value >= 0.85 ? "bg-accent" : value >= 0.6 ? "bg-warning" : "bg-border-strong"
      )}
    />
  );
}

export function ContactTable({
  contacts,
  emptyMessage = "No contacts yet.",
  openContactId,
  onCloseDetail,
  renderList = true,
}: {
  contacts: Contact[];
  emptyMessage?: string;
  /** Open the detail sheet for this contact on mount (used by the graph view). */
  openContactId?: string;
  onCloseDetail?: () => void;
  /** Set false to render only the detail sheet, with no list. */
  renderList?: boolean;
}) {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<Contact | null>(
    openContactId ? (contacts.find((c) => c.id === openContactId) ?? null) : null
  );
  const [draft, setDraft] = useState(
    openContactId
      ? (contacts.find((c) => c.id === openContactId)?.outreach_message ?? "")
      : ""
  );

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["campaign-contacts"] });
    qc.invalidateQueries({ queryKey: ["contacts"] });
    qc.invalidateQueries({ queryKey: ["balance"] });
  };

  const updateStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      contactsApi.update(id, { outreach_status: status }),
    onSuccess: invalidate,
    onError: (e: Error) => toast.error(e.message),
  });

  const saveMessage = useMutation({
    mutationFn: ({ id, message }: { id: string; message: string }) =>
      contactsApi.update(id, { outreach_message: message }),
    onSuccess: (updated) => {
      setSelected(updated);
      invalidate();
      toast.success("Message saved");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const redraft = useMutation({
    mutationFn: (id: string) => contactsApi.draftMessage(id),
    onSuccess: (updated) => {
      setSelected(updated);
      setDraft(updated.outreach_message ?? "");
      invalidate();
      toast.success("New draft written");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const open = (contact: Contact) => {
    setSelected(contact);
    setDraft(contact.outreach_message ?? "");
  };

  const closeDetail = () => {
    setSelected(null);
    onCloseDetail?.();
  };

  if (renderList && !contacts.length) {
    return (
      <Card>
        <CardContent className="py-14 text-center text-sm text-text-muted">
          {emptyMessage}
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      {renderList && (
        <Card className="overflow-hidden py-0">
          <div className="divide-y divide-border-subtle">
            {contacts.map((contact) => (
              <button
                key={contact.id}
                onClick={() => open(contact)}
                className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-sunk"
              >
                <ScoreDot score={contact.relevance_score} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{fullName(contact)}</div>
                  <div className="truncate text-xs text-text-muted">
                    {contact.title} · {contact.company}
                  </div>
                </div>
                <Badge variant={contact.outreach_status === "replied" ? "default" : "secondary"}>
                  {STATUSES.find((s) => s.value === contact.outreach_status)?.label ??
                    contact.outreach_status}
                </Badge>
              </button>
            ))}
          </div>
        </Card>
      )}

      <Sheet open={!!selected} onOpenChange={(o) => !o && closeDetail()}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-lg">
          {selected && (
            <>
              <SheetHeader>
                <SheetTitle>{fullName(selected)}</SheetTitle>
                <SheetDescription>
                  {selected.title} · {selected.company}
                </SheetDescription>
              </SheetHeader>

              <div className="space-y-6 px-4 pb-6">
                {selected.relevance_reasoning && (
                  <p className="rounded-lg bg-surface-sunk p-3 text-sm text-text-muted">
                    {selected.relevance_reasoning}
                  </p>
                )}

                <div className="space-y-2">
                  <label className="text-sm font-medium">Status</label>
                  <Select
                    value={selected.outreach_status}
                    onValueChange={(status) =>
                      updateStatus.mutate({ id: selected.id, status })
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {STATUSES.map((s) => (
                        <SelectItem key={s.value} value={s.value}>
                          {s.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-sm font-medium">Outreach message</label>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => redraft.mutate(selected.id)}
                      disabled={redraft.isPending}
                    >
                      <Sparkles className="h-3.5 w-3.5" />
                      {redraft.isPending ? "Writing…" : "Redraft"}
                    </Button>
                  </div>
                  <Textarea
                    rows={7}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    placeholder="No message drafted yet."
                  />
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        navigator.clipboard.writeText(draft);
                        toast.success("Copied");
                      }}
                      disabled={!draft}
                    >
                      <Copy className="h-3.5 w-3.5" />
                      Copy
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => saveMessage.mutate({ id: selected.id, message: draft })}
                      disabled={draft === (selected.outreach_message ?? "")}
                    >
                      Save
                    </Button>
                  </div>
                </div>

                {selected.linkedin_url && (
                  <Button asChild variant="outline" className="w-full">
                    <a href={selected.linkedin_url} target="_blank" rel="noreferrer">
                      <ExternalLink className="h-3.5 w-3.5" />
                      Open LinkedIn profile
                    </a>
                  </Button>
                )}
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </>
  );
}
