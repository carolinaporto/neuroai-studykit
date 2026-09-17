import { Route, Routes } from 'react-router-dom'

import { Layout } from './Layout'
import { HomeworkPage } from './pages/HomeworkPage'
import { NotesPage } from './pages/NotesPage'
import { OverviewPage } from './pages/OverviewPage'
import { QuizAttemptPage } from './pages/QuizAttemptPage'
import { QuizzesPage } from './pages/QuizzesPage'
import { SourcesPage } from './pages/SourcesPage'

function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<OverviewPage />} />
        <Route path="sources" element={<SourcesPage />} />
        <Route path="quizzes" element={<QuizzesPage />} />
        <Route path="quizzes/:attemptId" element={<QuizAttemptPage />} />
        <Route path="notes" element={<NotesPage />} />
        <Route path="homework" element={<HomeworkPage />} />
      </Route>
    </Routes>
  )
}

export default App
