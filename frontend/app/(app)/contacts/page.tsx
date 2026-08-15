"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { LayoutGrid, List, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ContactTable } from "@/components/contacts/ContactTable";
import { NetworkGraph } from "@/components/contacts/NetworkGraph";
import { campaigns, contacts as contactsApi, type Contact } from "@/lib/api";

const ALL = "__all__";

export default function ContactsPage() {
  const [campaignId, setCampaignId] = useState(ALL);
  const [status, setStatus] = useState(ALL);
  const [company, setCompany] = useState("");
  const [view, setView] = useState<"list" | "graph">("list");
  const [focused, setFocused] = useState<Contact | null>(null);

  const { data: campaignList } = useQuery({ queryKey: ["campaigns"], queryFn: campaigns.list });
  const { data, isLoading } = useQuery({
    queryKey: ["contacts", campaignId, status, company],
    queryFn: () =>
      contactsApi.list({
        campaign_id: campaignId === ALL ? undefined : campaignId,
        status: status === ALL ? undefined : status,
        company: company || undefined,
      }),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Contacts</h1>
        <p className="mt-1 text-sm text-text-muted">
          Everyone Sparrow has found, across every campaign.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <div className="relative min-w-[200px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-text-subtle" />
          <Input
            className="pl-9"
            placeholder="Filter by company"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
          />
        </div>

        <Select value={campaignId} onValueChange={setCampaignId}>
          <SelectTrigger className="w-[190px]">
            <SelectValue placeholder="All campaigns" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All campaigns</SelectItem>
            {(campaignList ?? []).map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="Any status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Any status</SelectItem>
            <SelectItem value="discovered">Discovered</SelectItem>
            <SelectItem value="message_drafted">Drafted</SelectItem>
            <SelectItem value="sent">Sent</SelectItem>
            <SelectItem value="replied">Replied</SelectItem>
            <SelectItem value="meeting_scheduled">Meeting</SelectItem>
          </SelectContent>
        </Select>

        <div className="flex rounded-lg border border-border-subtle p-0.5">
          <Button
            variant={view === "list" ? "secondary" : "ghost"}
            size="sm"
            onClick={() => setView("list")}
            aria-label="List view"
          >
            <List className="h-4 w-4" />
          </Button>
          <Button
            variant={view === "graph" ? "secondary" : "ghost"}
            size="sm"
            onClick={() => setView("graph")}
            aria-label="Graph view"
          >
            <LayoutGrid className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {isLoading ? (
        <Skeleton className="h-72" />
      ) : view === "graph" ? (
        <NetworkGraph
          contacts={data ?? []}
          onSelectContact={setFocused}
          selectedId={focused?.id ?? null}
        />
      ) : (
        <ContactTable
          contacts={data ?? []}
          emptyMessage="No contacts match these filters."
        />
      )}

      {/* Graph selection reuses the list's detail sheet rather than a second
          drawer implementation. */}
      {focused && (
        <ContactTable
          contacts={[focused]}
          openContactId={focused.id}
          onCloseDetail={() => setFocused(null)}
          renderList={false}
        />
      )}
    </div>
  );
}
