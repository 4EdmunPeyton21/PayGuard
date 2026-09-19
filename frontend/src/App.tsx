import { useEffect, useState } from 'react'
import CasePage from './pages/CasePage'
import InputPage from './pages/InputPage'
import TracePage from './pages/TracePage'

function App() {
  const [path, setPath] = useState(window.location.pathname)

  useEffect(() => {
    const onPopState = () => setPath(window.location.pathname)
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  if (path === '/analyzing' || /^\/case\/[^/]+\/trace\/?$/.test(path)) {
    return <TracePage />
  }
  const caseMatch = path.match(/^\/case\/([^/]+)\/?$/)
  if (caseMatch) {
    return <CasePage caseId={caseMatch[1]} />
  }
  return <InputPage />
}

export default App
