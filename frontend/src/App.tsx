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

  const page =
    path === '/analyzing' || /^\/case\/[^/]+\/trace\/?$/.test(path) ? (
      <TracePage />
    ) : (
      (() => {
        const caseMatch = path.match(/^\/case\/([^/]+)\/?$/)
        return caseMatch ? <CasePage caseId={caseMatch[1]} /> : <InputPage />
      })()
    )

  return (
    <>
      <div className="grain-overlay" />
      {page}
    </>
  )
}

export default App
