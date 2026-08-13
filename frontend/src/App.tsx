import { useQuery } from '@tanstack/react-query'
import { getHealth } from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

function App() {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
  })

  return (
    <div className="flex min-h-svh items-center justify-center bg-background p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Academic Degree Optimization Engine</CardTitle>
          <CardDescription>Phase 0 — local environment check</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-md border p-4 text-sm">
            {isLoading && <p>Checking backend health…</p>}
            {isError && (
              <p className="text-destructive">
                Could not reach backend: {(error as Error).message}
              </p>
            )}
            {data && (
              <p>
                Backend status:{' '}
                <span className="font-semibold text-primary">{data.status}</span>
              </p>
            )}
          </div>
          <Button onClick={() => refetch()} disabled={isFetching}>
            {isFetching ? 'Checking…' : 'Re-check backend'}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}

export default App
