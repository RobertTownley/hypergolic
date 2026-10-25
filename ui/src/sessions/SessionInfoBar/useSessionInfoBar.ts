import { useMemo, useState } from "react";
import { useAppDispatch, useAppSelector } from "@/store";
import { loadSessionContext } from "@/store/sessionsSlice";
import { fetchSessionPrompt, fetchSessionSkills } from "@/api/sessions";
import type { PromptPartInfo, SkillInfo, Session } from "@/types/api";
import type { TokenTotals, ChildSessionCost } from "@/modals/TokenCostModal";

const EMPTY: string[] = [];

const PRICING: Record<string, { input: number; output: number; cacheWrite: number; cacheRead: number }> = {
  Low:    { input: 1,  output: 5,   cacheWrite: 1.25, cacheRead: 0.10 },
  Medium: { input: 3,  output: 15,  cacheWrite: 3.75, cacheRead: 0.30 },
  High:   { input: 5,  output: 25,  cacheWrite: 6.25, cacheRead: 0.50 },
  "Extra High": { input: 10, output: 50, cacheWrite: 12.5, cacheRead: 1.0 },
};

function computeTokenTotals(messages: { usage?: { input_tokens?: number; output_tokens?: number; cache_creation_input_tokens?: number; cache_read_input_tokens?: number } | null }[], modelTier: string): TokenTotals {
  let inputTokens = 0;
  let outputTokens = 0;
  let cacheCreation = 0;
  let cacheRead = 0;

  for (const msg of messages) {
    if (msg.usage) {
      inputTokens += msg.usage.input_tokens ?? 0;
      outputTokens += msg.usage.output_tokens ?? 0;
      cacheCreation += msg.usage.cache_creation_input_tokens ?? 0;
      cacheRead += msg.usage.cache_read_input_tokens ?? 0;
    }
  }

  const rates = PRICING[modelTier] ?? PRICING.High;
  const inputCost = (inputTokens / 1_000_000) * rates.input;
  const outputCost = (outputTokens / 1_000_000) * rates.output;
  const cacheWriteCost = (cacheCreation / 1_000_000) * rates.cacheWrite;
  const cacheReadCost = (cacheRead / 1_000_000) * rates.cacheRead;
  const totalCost = inputCost + outputCost + cacheWriteCost + cacheReadCost;

  return {
    inputTokens, outputTokens, cacheCreation, cacheRead,
    inputCost, outputCost, cacheWriteCost, cacheReadCost, totalCost,
    modelTier,
  };
}

export function useTokenTotals() {
  const activeSessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const messages = useAppSelector(
    (s) => (activeSessionId ? s.messages.bySessionId[activeSessionId] : undefined) ?? [],
  );
  const modelTier = useAppSelector(
    (s) => (activeSessionId ? s.sessions.entities[activeSessionId]?.model_tier : undefined) ?? "High",
  );

  return useMemo(() => computeTokenTotals(messages, modelTier), [messages, modelTier]);
}

export function useChildSessionCosts(): { childCosts: ChildSessionCost[]; totalChildCost: number } {
  const activeSessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const entities = useAppSelector((s) => s.sessions.entities);
  const messagesBySessionId = useAppSelector((s) => s.messages.bySessionId);

  return useMemo(() => {
    if (!activeSessionId) return { childCosts: [], totalChildCost: 0 };

    const childCosts: ChildSessionCost[] = [];
    let totalChildCost = 0;

    for (const [sessionId, session] of Object.entries(entities)) {
      const typedSession = session as Session | undefined;
      if (typedSession?.parent_id !== activeSessionId) continue;
      const messages = messagesBySessionId[sessionId] ?? [];
      const modelTier = typedSession.model_tier ?? "High";
      const totals = computeTokenTotals(messages, modelTier);
      childCosts.push({ sessionId, modelTier, totals });
      totalChildCost += totals.totalCost;
    }

    return { childCosts, totalChildCost };
  }, [activeSessionId, entities, messagesBySessionId]);
}

export function useSkills() {
  const activeSessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const context = useAppSelector(
    (s) => (activeSessionId ? s.sessions.contextBySessionId[activeSessionId] : undefined),
  );
  const [modalOpen, setModalOpen] = useState(false);
  const [skills, setSkills] = useState<SkillInfo[]>([]);

  const handleOpen = () => {
    if (activeSessionId) {
      fetchSessionSkills(activeSessionId).then(setSkills);
    }
    setModalOpen(true);
  };

  const handleClose = () => {
    setModalOpen(false);
    setSkills([]);
  };

  const totalCount = skills.length > 0 ? skills.length : (context?.skills_summary.total ?? 0);
  // Server-side record (refreshed with the context at turn end), not the
  // transcript: compaction drops the activation call, the DB row stays.
  const activated = context?.skills_summary.activated ?? EMPTY;

  return { modalOpen, skills, totalCount, activated, handleOpen, handleClose };
}

export function useTools() {
  const dispatch = useAppDispatch();
  const activeSessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const context = useAppSelector(
    (s) => (activeSessionId ? s.sessions.contextBySessionId[activeSessionId] : undefined),
  );
  const [modalOpen, setModalOpen] = useState(false);

  const handleOpen = () => {
    if (activeSessionId) {
      dispatch(loadSessionContext(activeSessionId));
    }
    setModalOpen(true);
  };

  const handleClose = () => {
    setModalOpen(false);
  };

  const tools = context?.tools ?? [];
  const toolCount = context?.tools_count ?? 0;
  const tokenEstimate = context?.tools_token_estimate ?? 0;

  const formatCount = (n: number) => {
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
    return n.toString();
  };

  return { modalOpen, tools, toolCount, tokenEstimate, formatCount, handleOpen, handleClose };
}

export function useSystemPrompt() {
  const activeSessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const context = useAppSelector(
    (s) => (activeSessionId ? s.sessions.contextBySessionId[activeSessionId] : undefined),
  );
  const [modalOpen, setModalOpen] = useState(false);
  const [parts, setParts] = useState<PromptPartInfo[]>([]);

  const handleOpen = () => {
    if (activeSessionId) {
      fetchSessionPrompt(activeSessionId).then(setParts);
    }
    setModalOpen(true);
  };

  const handleClose = () => {
    setModalOpen(false);
    setParts([]);
  };

  const totalTokens = useMemo(
    () => parts.length > 0 ? parts.reduce((sum, p) => sum + p.token_estimate, 0) : (context?.prompt_token_estimate ?? 0),
    [parts, context],
  );

  const formatCount = (n: number) => {
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
    return n.toString();
  };

  return { modalOpen, parts, totalTokens, formatCount, handleOpen, handleClose };
}
