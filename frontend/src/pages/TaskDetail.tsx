import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, RotateCcw, Download, Loader2 } from 'lucide-react';
import { apiFetch, streamTask } from '@/lib/api';
import { useToast } from '@/components/Toast';
import { useEffect, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';

interface Task {
  id: string;
  instruction: string;
  status: string;
  created_at: string;
  completed_at: string | null;
  token_usage: number;
  token_budget: number;
  error_message: string | null;
  subtasks: { id: string; description: string; tool: string; order: number }[];
}

export default function TaskDetail() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { addToast } = useToast();
  const [liveTask, setLiveTask] = useState<Task | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const { data: task, isLoading } = useQuery({
    queryKey: ['task', taskId],
    queryFn: async () => {
      const res = await apiFetch(`/tasks/${taskId}`);
      if (!res.ok) throw new Error('Task not found');
      return res.json() as Promise<Task>;
    },
    enabled: !!taskId,
  });

  const displayedTask = liveTask || task;

  useEffect(() => {
    if (displayedTask?.status === 'running' || displayedTask?.status === 'planning') {
      controllerRef.current = streamTask(
        taskId!,
        (data: Task) => setLiveTask(data),
        () => queryClient.invalidateQueries({ queryKey: ['task', taskId] }),
      );
      return () => controllerRef.current?.abort();
    }
  }, [taskId, displayedTask?.status]);

  const revertMutation = useMutation({
    mutationFn: async () => {
      const res = await apiFetch(`/tasks/${taskId}/revert`, { method: 'POST' });
      if (!res.ok) throw new Error('Revert failed');
      return res.json();
    },
    onSuccess: (data: any) => {
      addToast(`Reverted ${data.count || 0} actions`, 'success');
      queryClient.invalidateQueries({ queryKey: ['task', taskId] });
    },
    onError: (err: Error) => addToast(err.message, 'error'),
  });

  const exportMutation = useMutation({
    mutationFn: async () => {
      const res = await apiFetch(`/tasks/${taskId}/ledger/export`);
      if (!res.ok) throw new Error('Export failed');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ledger-${taskId}.jsonl`;
      a.click();
      URL.revokeObjectURL(url);
    },
    onError: (err: Error) => addToast(err.message, 'error'),
  });

  if (isLoading) return <p className="text-muted-foreground">Loading...</p>;
  if (!displayedTask) return <p className="text-destructive">Task not found</p>;

  const isRunning = displayedTask.status === 'running' || displayedTask.status === 'planning';

  return (
    <div className="max-w-3xl mx-auto">
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Back
      </button>

      <div className="flex items-start justify-between mb-6">
        <div className="flex-1">
          <h1 className="text-xl font-bold mb-1">{displayedTask.instruction}</h1>
          <p className="text-xs text-muted-foreground flex items-center gap-2">
            {new Date(displayedTask.created_at).toLocaleString()}
            <span className="capitalize inline-flex items-center gap-1">
              {isRunning && <Loader2 className="w-3 h-3 animate-spin" />}
              {displayedTask.status}
            </span>
            {displayedTask.token_usage > 0 && (
              <span>Tokens: {displayedTask.token_usage}/{displayedTask.token_budget}</span>
            )}
          </p>
          {displayedTask.error_message && (
            <p className="text-xs text-destructive mt-1">{displayedTask.error_message}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => exportMutation.mutate()}
            disabled={exportMutation.isPending}
            className="flex items-center gap-2 border border-border px-3 py-2 rounded-md text-sm hover:bg-secondary transition-colors disabled:opacity-50"
          >
            <Download className="w-4 h-4" />
            Export
          </button>
          <button
            onClick={() => revertMutation.mutate()}
            disabled={revertMutation.isPending}
            className="flex items-center gap-2 border border-border px-3 py-2 rounded-md text-sm hover:bg-secondary transition-colors disabled:opacity-50"
          >
            <RotateCcw className="w-4 h-4" />
            Revert
          </button>
        </div>
      </div>

      {displayedTask.subtasks && displayedTask.subtasks.length > 0 ? (
        <div className="space-y-2">
          {[...displayedTask.subtasks]
            .sort((a, b) => a.order - b.order)
            .map((sub, idx) => (
              <div
                key={sub.id}
                className="flex items-center gap-3 border border-border rounded-md px-4 py-3"
              >
                <span className="text-xs text-muted-foreground font-mono w-6">{idx + 1}</span>
                <div className="flex-1">
                  <p className="text-sm font-medium">{sub.description}</p>
                  <p className="text-xs text-muted-foreground capitalize">{sub.tool}</p>
                </div>
              </div>
            ))}
        </div>
      ) : (
        <div className="py-12 text-center">
          <Loader2 className="w-6 h-6 text-muted-foreground mx-auto mb-3 animate-spin" />
          <p className="text-muted-foreground text-sm">
            {isRunning ? 'Task is being planned...' : 'No subtasks yet.'}
          </p>
        </div>
      )}
    </div>
  );
}
