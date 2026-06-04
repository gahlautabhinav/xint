import { Route, Routes } from "react-router-dom";
import { NavBar } from "./components/NavBar";
import { GraphExplorer } from "./features/graph/GraphExplorer";
import { JobsPage } from "./features/jobs/JobsPage";
import { AccountsPage } from "./features/accounts/AccountsPage";

export function App() {
  return (
    <div className="app">
      <NavBar />
      <main className="app__main">
        <Routes>
          <Route path="/" element={<GraphExplorer />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/jobs/:jobId" element={<JobsPage />} />
          <Route path="/accounts" element={<AccountsPage />} />
          <Route path="*" element={<GraphExplorer />} />
        </Routes>
      </main>
    </div>
  );
}
