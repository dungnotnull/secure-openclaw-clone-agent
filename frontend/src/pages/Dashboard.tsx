import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ArrowRight, PlusCircle } from 'lucide-react';
import { apiFetch } from '@/lib/api';

interface Task {
  id: string;
  instruction: string;
  status: string;
  created_at: string;
}

export default function Dashboard() {
  const { data: tasks, isLoading, error } = useQuery({
    queryKey: ['tasks'],
    queryFn: async () => {
      const res = await apiFetch('/tasks');
      if (!res.ok) throw new Error('Failed to fetch tasks');
      return res.json() as Promise<Task[]>;
    },
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <Link
          to="/tasks/new"
          className="inline-flex items-center gap-2 bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm font-medium"
        >
          <PlusCircle className="w-4 h-4" />
          New Task
        </Link>
      </div>

      {isLoading ? (
        <p className="text-muted-foreground">Loading tasks...</p>
      ) : error ? (
        <p className="text-destructive text-sm">Failed to load tasks.</p>
      ) : !tasks || tasks.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-muted-foreground mb-4">No tasks yet.</p>
          <Link to="/tasks/new" className="text-primary hover:underline text-sm">
            Create your first task
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {tasks.map(task => (
            <Link
              key={task.id}
              to={`/tasks/${task.id}`}
              className="block border border-border rounded-lg p-4 hover:bg-card/50 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm truncate">{task.instruction}</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {new Date(task.created_at).toLocaleString()} &middot;{' '}
                    <span className="capitalize">{task.status}</span>
                  </p>
                </div>
                <ArrowRight className="w-4 h-4 text-muted-foreground ml-4 flex-shrink-0" />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
