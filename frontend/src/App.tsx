import { Toaster } from "sonner";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Sidebar } from "./components/Sidebar";
import { CampaignsPage } from "./pages/Campaigns";
import { MessagePage } from "./pages/Message";
import { RecipientsPage } from "./pages/Recipients";
import { SendPage } from "./pages/Send";
import { SettingsPage } from "./pages/Settings";
import { TrackingPage } from "./pages/Tracking";
import { useStore } from "./store";

declare global {
  interface Window {
    __automailCrash?: string;
  }
}

/** Pour les tests de bout en bout : fait planter l'écran demandé (inerte sinon). */
function CrashProbe({ page }: { page: string }) {
  if (window.__automailCrash === page) throw new Error(`Plantage de test sur l'écran « ${page} »`);
  return null;
}

export default function App() {
  const { page, campaign, theme, go } = useStore();
  const needsCampaign = page !== "campaigns" && page !== "settings";
  const shown = needsCampaign && !campaign ? "campaigns" : page;
  const wide = shown === "message" || shown === "tracking";

  return (
    <div className="flex h-full">
      <Sidebar />
      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className={wide ? "mx-auto max-w-[1500px] px-8 py-8" : "mx-auto max-w-5xl px-8 py-8"}>
          {/* Un écran qui plante n'emporte ni la sidebar ni le reste de l'appli. */}
          <ErrorBoundary page={shown} onHome={() => go("campaigns")}>
            <div key={shown + (campaign?.id ?? "")} className="animate-rise">
              <CrashProbe page={shown} />
              {shown === "campaigns" && <CampaignsPage />}
              {shown === "recipients" && <RecipientsPage />}
              {shown === "message" && <MessagePage />}
              {shown === "send" && <SendPage />}
              {shown === "tracking" && <TrackingPage />}
              {shown === "settings" && <SettingsPage />}
            </div>
          </ErrorBoundary>
        </div>
      </main>
      <Toaster
        position="bottom-right"
        theme={theme}
        richColors
        closeButton
        toastOptions={{ style: { fontFamily: "var(--font-sans)", borderRadius: 14 } }}
      />
    </div>
  );
}
