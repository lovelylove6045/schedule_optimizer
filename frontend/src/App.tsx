import { useCallback, useState } from "react"
import { Route, Routes } from "react-router-dom"
import { AppShell } from "@/components/layout/app-shell"
import { PathfinderIntro } from "@/components/layout/pathfinder-intro"
import { Toaster } from "@/components/ui/sonner"
import { WizardPage } from "@/pages/wizard-page"
import { PlansPage } from "@/pages/plans-page"
import { CatalogPage } from "@/pages/catalog-page"
import { CoursesPage } from "@/pages/courses-page"

/** Mount the unchanged route table beneath one per-page-load product introduction. */
function App() {
  const [introMounted, setIntroMounted] = useState(true)
  const [introBlocking, setIntroBlocking] = useState(true)
  /** Make the existing application interactive as soon as the intro begins leaving. */
  const handleIntroExitStart = useCallback(() => setIntroBlocking(false), [])
  /** Remove the faded intro overlay after its short exit transition. */
  const handleIntroComplete = useCallback(() => setIntroMounted(false), [])
  return (
    <>
      <div inert={introBlocking} aria-hidden={introBlocking || undefined}>
        <AppShell>
          <Routes>
            <Route path="/" element={<WizardPage />} />
            <Route path="/plans/:scenarioId" element={<PlansPage />} />
            <Route path="/catalog" element={<CatalogPage />} />
            <Route path="/courses" element={<CoursesPage />} />
          </Routes>
          <Toaster />
        </AppShell>
      </div>
      {introMounted ? <PathfinderIntro onExitStart={handleIntroExitStart} onComplete={handleIntroComplete} /> : null}
    </>
  )
}

export default App
