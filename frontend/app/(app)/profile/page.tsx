"use client";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { FileText, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { profile, settingsApi } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function ProfilePage() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const { data: prefs } = useQuery({ queryKey: ["settings"], queryFn: settingsApi.get });
  const { data: resume } = useQuery({
    queryKey: ["resume"],
    queryFn: profile.active,
    retry: false,
  });

  // Edits are held as an overlay on the fetched values. Syncing server data into
  // state via an effect would cascade a render on every refetch and clobber an
  // in-progress edit; `null` here means "not edited yet, show what the server has".
  const [headlineEdit, setHeadlineEdit] = useState<string | null>(null);
  const [valuePropEdit, setValuePropEdit] = useState<string | null>(null);

  const headline = headlineEdit ?? prefs?.headline ?? "";
  const valueProp = valuePropEdit ?? prefs?.value_prop ?? "";
  const setHeadline = setHeadlineEdit;
  const setValueProp = setValuePropEdit;

  const save = useMutation({
    mutationFn: () => settingsApi.update({ headline, value_prop: valueProp }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      qc.invalidateQueries({ queryKey: ["dashboard-stats"] });
      // Drop the overlay so the saved server values become the source of truth.
      setHeadlineEdit(null);
      setValuePropEdit(null);
      toast.success("Profile saved");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const upload = useMutation({
    mutationFn: (file: File) => profile.upload(file),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["resume"] });
      qc.invalidateQueries({ queryKey: ["dashboard-stats"] });
      toast.success("Background uploaded");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const remove = useMutation({
    mutationFn: (id: string) => profile.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["resume"] });
      toast.success("Removed");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const dirty = headline !== (prefs?.headline ?? "") || valueProp !== (prefs?.value_prop ?? "");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Profile</h1>
        <p className="mt-1 text-sm text-text-muted">
          Everything here goes into the messages Sparrow writes on your behalf.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">How you introduce yourself</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="headline">Headline</Label>
            <Input
              id="headline"
              value={headline}
              onChange={(e) => setHeadline(e.target.value)}
              placeholder="Co-founder at Kestrel — observability for data teams"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="value-prop">What you offer</Label>
            <p className="text-xs text-text-subtle">
              The reason someone should reply. Be concrete — this is the sentence that has to do
              the work.
            </p>
            <Textarea
              id="value-prop"
              rows={3}
              value={valueProp}
              onChange={(e) => setValueProp(e.target.value)}
              placeholder="We cut alert noise by ~70% for data platform teams running dbt and Airflow."
            />
          </div>
          <div className="flex justify-end">
            <Button disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
              {save.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Background</CardTitle>
        </CardHeader>
        <CardContent>
          {resume ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-3 rounded-lg border border-border-subtle bg-surface-sunk p-3">
                <div className="flex min-w-0 items-center gap-3">
                  <FileText className="h-4 w-4 shrink-0 text-text-subtle" />
                  <span className="truncate text-sm">{resume.filename}</span>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => remove.mutate(resume.id)}
                  disabled={remove.isPending}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>

              {resume.structured_data?.skills?.length ? (
                <div className="flex flex-wrap gap-1.5">
                  {resume.structured_data.skills.slice(0, 20).map((skill) => (
                    <span
                      key={skill}
                      className="rounded-md bg-surface-sunk px-2 py-1 text-xs text-text-muted"
                    >
                      {skill}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ) : (
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                const file = e.dataTransfer.files?.[0];
                if (file) upload.mutate(file);
              }}
              onClick={() => fileRef.current?.click()}
              className={cn(
                "flex cursor-pointer flex-col items-center gap-3 rounded-lg border border-dashed p-10 text-center transition-colors",
                dragging ? "border-accent bg-accent-soft" : "border-border-strong hover:bg-surface-sunk"
              )}
            >
              <Upload className="h-5 w-5 text-text-subtle" />
              <div>
                <p className="text-sm font-medium">
                  {upload.isPending ? "Uploading…" : "Drop a resume or CV"}
                </p>
                <p className="mt-1 text-xs text-text-muted">
                  PDF or DOCX. Sparrow reads it for context, not to send anywhere.
                </p>
              </div>
              <input
                ref={fileRef}
                type="file"
                accept=".pdf,.docx"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) upload.mutate(file);
                }}
              />
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
