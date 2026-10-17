import { CheckCircle2, ExternalLink, KeyRound, Lock, PlugZap, Save, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "../api";
import { Badge, Button, Card, Field, Input, PageHeader, Segmented, Spinner } from "../components/ui";
import { useStore } from "../store";
import type { Settings } from "../types";

export function SettingsPage() {
  const { settings, setSettings, theme, setTheme } = useStore();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  useEffect(() => {
    if (!settings) return;
    setEmail(settings.email);
    setName(settings.display_name);
  }, [settings]);

  const dirty = !!settings && (email.trim() !== settings.email || name.trim() !== settings.display_name || !!password);

  const save = async () => {
    setSaving(true);
    try {
      let s = await api.saveSettings({ email: email.trim(), display_name: name.trim() });
      if (password) s = await api.savePassword(password);
      setSettings(s);
      setPassword("");
      toast.success("Compte enregistré", { description: password ? "Mot de passe rangé dans le Gestionnaire d'identification Windows." : undefined });
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    setTesting(true);
    setResult(null);
    try {
      const r = await api.testAccount({ email: email.trim(), password: password || undefined });
      setResult(r);
    } catch (e) {
      setResult({ ok: false, message: (e as Error).message });
    } finally {
      setTesting(false);
    }
  };

  const forget = async () => {
    try {
      setSettings(await api.savePassword(""));
      toast.success("Mot de passe oublié");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <>
      <PageHeader title="Réglages" description="Ton compte Gmail et l'apparence de l'application." />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Card className="p-6">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold">Compte Gmail</h2>
            {settings?.has_password ? <Badge tone="ok"><Lock size={11} /> Mot de passe enregistré</Badge> : <Badge tone="accent">À configurer</Badge>}
          </div>
          <div className="mt-5 space-y-4">
            <Field label="Adresse Gmail">
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="prenom.nom@gmail.com" autoComplete="off" />
            </Field>
            <Field label="Nom affiché" hint="Ce que les destinataires voient comme expéditeur.">
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Thomas Leman" />
            </Field>
            <Field
              label="Mot de passe d'application"
              hint={
                <>
                  16 caractères générés par Google (pas ton mot de passe habituel).{" "}
                  <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 font-semibold text-accent hover:underline">
                    En créer un <ExternalLink size={11} />
                  </a>
                </>
              }
            >
              <div className="relative">
                <KeyRound size={15} className="absolute top-1/2 left-3 -translate-y-1/2 text-muted" />
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={settings?.has_password ? "•••• •••• •••• •••• (inchangé)" : "abcd efgh ijkl mnop"}
                  className="pl-9 font-mono"
                  autoComplete="new-password"
                />
              </div>
            </Field>
          </div>

          {result && (
            <div className={`mt-5 flex items-start gap-2 rounded-xl p-3 text-sm ${result.ok ? "bg-ok-soft text-ok" : "bg-bad-soft text-bad"}`}>
              {result.ok ? <CheckCircle2 size={17} className="mt-0.5 shrink-0" /> : <XCircle size={17} className="mt-0.5 shrink-0" />}
              {result.message}
            </div>
          )}

          <div className="mt-6 flex flex-wrap items-center gap-2">
            <Button variant="primary" icon={saving ? <Spinner /> : <Save size={16} />} disabled={!dirty || saving || !email.trim()} onClick={save}>
              Enregistrer
            </Button>
            <Button icon={testing ? <Spinner /> : <PlugZap size={16} />} disabled={testing || !email.trim() || (!password && !settings?.has_password)} onClick={test}>
              Tester la connexion
            </Button>
            {settings?.has_password && (
              <Button variant="ghost" className="ml-auto text-bad" onClick={forget}>
                Oublier le mot de passe
              </Button>
            )}
          </div>
          <p className="mt-4 flex items-start gap-2 text-xs text-muted">
            <Lock size={13} className="mt-0.5 shrink-0" />
            Le mot de passe est rangé dans le Gestionnaire d'identification de Windows, jamais dans un fichier.
          </p>
        </Card>

        <div className="space-y-5">
          <Card className="p-6">
            <h2 className="text-base font-bold">Apparence</h2>
            <div className="mt-4">
              <Segmented<Settings["theme"]>
                value={theme}
                onChange={setTheme}
                options={[
                  { value: "light", label: "Clair" },
                  { value: "dark", label: "Sombre" },
                  { value: "system", label: "Système" },
                ]}
              />
            </div>
          </Card>
          <Card className="p-6">
            <h2 className="text-base font-bold">Données</h2>
            <p className="mt-2 text-sm text-muted">Campagnes, suivis et réglages sont rangés ici :</p>
            <code className="mt-2 block rounded-lg bg-surface-2 px-3 py-2 font-mono text-xs break-all">{settings?.data_dir}</code>
          </Card>
        </div>
      </div>
    </>
  );
}
