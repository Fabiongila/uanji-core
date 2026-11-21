import { Eraser, FileText, Settings2 } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { useAssistantStatus, useHealth } from "@/api/hooks";
import { CoreOrb, useCoreState } from "@/components/CoreOrb";
import { Badge, Button, PageHeader, Panel } from "@/components/ui";
import { AssistantInput, ListeningToggle, MicButton, SpeechControls, TurnView, VoiceIndicators } from "@/features/assistant";
import { sendMessage, useVoice } from "@/lib/voice";

const QUICK = [
  { label: "Relatório do dia", text: "faz o relatório do meu dia" },
  { label: "Prioridades", text: "quais são as minhas tarefas prioritárias de hoje?" },
  { label: "Projecto mais atrasado", text: "qual dos meus projectos está mais atrasado?" },
  { label: "Problemas", text: "explica-me os principais problemas encontrados" },
  { label: "Automações falhadas", text: "mostra-me as automações que falharam" },
  { label: "Revisão semanal", text: "prepara a minha revisão semanal" },
];

export default function AssistantPage() {
  const status = useVoice((s) => s.status);
  const entries = useVoice((s) => s.entries);
  const partial = useVoice((s) => s.partial);
  const clear = useVoice((s) => s.clear);
  const ai = useAssistantStatus();
  const health = useHealth();
  const core = useCoreState(health.isError);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [entries.length, partial]);

  return (
    <div className="mx-auto flex h-full max-w-[1200px] flex-col gap-3">
      <PageHeader
        title="Assistente UANJI"
        subtitle={
          ai.data?.configured
            ? `Interpretação local + fornecedor de IA (${ai.data.provider}) para pedidos abertos.`
            : "Interpretação local, sem Internet. Configure um fornecedor de IA para conversa livre (opcional)."
        }
        actions={
          <>
            <Badge tone={ai.data?.configured ? "success" : "neutral"}>{ai.data?.configured ? "IA configurada" : "Sem IA"}</Badge>
            <Link to="/settings#voz">
              <Button size="sm" variant="ghost" icon={<Settings2 className="h-3.5 w-3.5" />}>
                Voz e personalidade
              </Button>
            </Link>
          </>
        }
      />
      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[300px_1fr]">
        <div className="flex flex-col gap-3">
          <section className="holo-card items-center" aria-label="Núcleo do assistente">
            <div className="holo-scan" aria-hidden />
            <div className="relative z-10 flex flex-col items-center gap-3 p-4">
              <CoreOrb state={core} size={190} />
              <div className="flex items-center gap-3">
                <MicButton status={status} size="lg" />
                <ListeningToggle status={status} />
              </div>
              <p className="text-center text-[11.5px] text-muted">
                {status?.listening_enabled
                  ? `Diga «${status.wake_word}» e depois o pedido. Esc interrompe a fala.`
                  : "Carregue no microfone para falar, ou escreva abaixo."}
              </p>
              <SpeechControls status={status} />
            </div>
          </section>
          <Panel title="Privacidade e estado">
            <VoiceIndicators status={status} />
            {status && !status.stt.model_installed && (
              <p className="mt-2 text-[12px] text-amber">
                O reconhecimento de fala local ainda não está instalado. <Link to="/settings#voz" className="underline">Instalar em Definições</Link>.
              </p>
            )}
          </Panel>
          <Panel title="Pedidos rápidos">
            <div className="flex flex-wrap gap-1.5">
              {QUICK.map((q) => (
                <Button key={q.text} size="sm" variant="secondary" icon={<FileText className="h-3 w-3" />} onClick={() => void sendMessage(q.text, true).catch(() => undefined)}>
                  {q.label}
                </Button>
              ))}
            </div>
          </Panel>
        </div>
        <div className="flex min-h-0 flex-col gap-3">
          <Panel
            title="Conversa"
            className="min-h-[320px] flex-1"
            bodyClassName="flex flex-col gap-3 overflow-y-auto"
            actions={
              entries.length > 0 && (
                <Button size="sm" variant="ghost" icon={<Eraser className="h-3 w-3" />} onClick={clear} title="Começa uma conversa nova (o histórico guardado mantém-se conforme a retenção definida)">
                  Nova conversa
                </Button>
              )
            }
          >
            {entries.length === 0 && (
              <div className="text-[13px] text-muted">
                <p>Exemplos do que pode pedir, por voz ou texto:</p>
                <ul className="mt-1 list-inside list-disc">
                  <li>«Cria uma tarefa para rever a autenticação do Q360.»</li>
                  <li>«Regista esta ideia nas minhas notas.»</li>
                  <li>«Abre o projecto Gestão Escolar.» → «O que está a bloquear este projecto?»</li>
                  <li>«Cria uma checklist para publicar uma API Django.»</li>
                  <li>«Repete», «Cancela», «Sim» / «Não» para confirmar.</li>
                </ul>
              </div>
            )}
            {entries.map((e) => (
              <TurnView key={e.id} entry={e} />
            ))}
            {partial && (
              <div className="flex justify-end">
                <div className="max-w-[85%] rounded-lg border border-dashed border-electric/40 px-3 py-2 text-[13px] italic text-electric">{partial}…</div>
              </div>
            )}
            <div ref={end} />
          </Panel>
          <AssistantInput autoFocus />
        </div>
      </div>
    </div>
  );
}
