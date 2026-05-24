import { Navigate, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { Sidebar } from "@/components/Sidebar";
import { useDevMode } from "@/hooks/useDevMode";
import ParcelsScreen from "@/screens/Parcels";
import SourcesScreen from "@/screens/Sources";
import PreferencesScreen from "@/screens/Preferences";
import DiagnosticsScreen from "@/screens/Diagnostics";

export default function App() {
  const [devMode, setDevMode] = useDevMode();

  // Drive the "Online" indicator from /api/status (cheap probe).
  const status = useQuery({
    queryKey: ["status"],
    queryFn: api.getStatus,
    refetchInterval: 30_000,
  });

  const online = status.data !== undefined && !status.isError;

  return (
    <>
      <Sidebar
        online={online}
        devMode={devMode}
        onToggleDev={setDevMode}
      />
      <main className="content">
        <Routes>
          <Route path="/" element={<Navigate to="/parcels" replace />} />
          <Route path="/parcels" element={<ParcelsScreen />} />
          <Route path="/sources" element={<SourcesScreen />} />
          <Route path="/preferences" element={<PreferencesScreen />} />
          {devMode && (
            <Route path="/diagnostics" element={<DiagnosticsScreen />} />
          )}
          <Route path="*" element={<Navigate to="/parcels" replace />} />
        </Routes>
      </main>
    </>
  );
}
