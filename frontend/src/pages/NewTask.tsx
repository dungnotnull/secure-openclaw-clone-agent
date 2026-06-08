import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Shield } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import { useToast } from '@/components/Toast';

export default function NewTask() {
  const [instruction, setInstruction] = useState('');
  const [budget, setBudget] = useState(100000);
  const [submitting, setSubmitting] = useState(false);
  const { addToast } = useToast();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!instruction.trim()) return;
    setSubmitting(true);
    try {
      const res = await apiFetch('/tasks', {
        method: 'POST',
        body: JSON.stringify({ instruction, token_budget: budget }),
      });
      if (!res.ok) throw new Error('Failed to create task');
      const task = await res.json();
      navigate(`/tasks/${task.id}`);
    } catch (err: any) {
      addToast(err.message || 'Failed to create task', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold mb-2">New Task</h1>
      <p className="text-sm text-muted-foreground mb-6">
        Describe what you want the agent to do. All actions run in an isolated sandbox with encryption at rest.
      </p>
      <form onSubmit={handleSubmit} className="space-y-4">
        <textarea
          value={instruction}
          onChange={e => setInstruction(e.target.value)}
          placeholder="e.g., Refactor the auth module to use JWT tokens, create a test suite for the API endpoints..."
          rows={6}
          className="w-full border border-input bg-background rounded-md px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-none"
        />
        <div className="flex items-center gap-4">
          <label className="text-xs text-muted-foreground flex items-center gap-2">
            Token budget:
            <input
              type="number"
              value={budget}
              onChange={e => setBudget(Number(e.target.value))}
              className="border border-input bg-background rounded px-2 py-1 text-sm w-24"
              min={1000}
              max={1000000}
            />
          </label>
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Shield className="w-4 h-4" />
            <span>Sandboxed &amp; encrypted execution</span>
          </div>
          <button
            type="submit"
            disabled={submitting || !instruction.trim()}
            className="bg-primary text-primary-foreground px-6 py-2 rounded-md text-sm font-medium disabled:opacity-50"
          >
            {submitting ? 'Submitting...' : 'Submit Task'}
          </button>
        </div>
      </form>
    </div>
  );
}
