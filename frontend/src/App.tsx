import { Route, Routes } from "react-router-dom"
import { AppShell } from "@/components/layout/app-shell"
import { Toaster } from "@/components/ui/sonner"
import { WizardPage } from "@/pages/wizard-page"
import { PlansPage } from "@/pages/plans-page"
import { CatalogPage } from "@/pages/catalog-page"
import { CoursesPage } from "@/pages/courses-page"

/** Top-level route table: the wizard at "/", tabbed results at "/plans/:scenarioId",
 * and the read-only catalog browser at "/catalog". */
function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<WizardPage />} />
        <Route path="/plans/:scenarioId" element={<PlansPage />} />
        <Route path="/catalog" element={<CatalogPage />} />
        <Route path="/courses" element={<CoursesPage />} />
      </Routes>
      <Toaster />
    </AppShell>
  )
}

export default App
