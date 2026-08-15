import { Route, Routes } from "react-router-dom"
import { AppShell } from "@/components/layout/app-shell"
import { WizardPage } from "@/pages/wizard-page"
import { PlansPage } from "@/pages/plans-page"

/** Top-level route table: the wizard at "/" and tabbed results at "/plans/:scenarioId". */
function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<WizardPage />} />
        <Route path="/plans/:scenarioId" element={<PlansPage />} />
      </Routes>
    </AppShell>
  )
}

export default App
