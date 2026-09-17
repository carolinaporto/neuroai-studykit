import { useQuery } from '@tanstack/react-query'

import { listHomework } from '../api/client'
import { HomeworkCard } from '../components/HomeworkCard'
import './HomeworkPage.css'

export function HomeworkPage() {
  const query = useQuery({ queryKey: ['homework'], queryFn: listHomework })

  if (query.isLoading) return <p className="body">Loading…</p>
  if (query.isError) return <p className="body">{(query.error as Error).message}</p>

  const homework = query.data ?? []

  return (
    <div className="page">
      <h1 className="h1">Homework</h1>
      {homework.length === 0 && <p className="body">Nothing published yet.</p>}
      <div className="homework-grid">
        {homework.map((entry) => (
          <HomeworkCard key={entry.id} {...entry} />
        ))}
      </div>
    </div>
  )
}
