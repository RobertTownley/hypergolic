import { useMemo, useReducer, useRef, type Dispatch, type SetStateAction } from "react";
import type { FileContentResponse, Message } from "@/types/api";
import type { FinderMode, FinderResult } from "../types";

interface FinderState {
  open: boolean;
  query: string;
  mode: FinderMode;
  respectGitignore: boolean;
  includeHidden: boolean;
  results: FinderResult[];
  selectedIndex: number;
  loading: boolean;
  filePreview: FileContentResponse | null;
  filePreviewLoading: boolean;
  filePreviewError: string | null;
  sessionMessages: Message[] | null;
  sessionPreviewLoading: boolean;
}

type FinderAction = {
  [K in keyof FinderState]: { key: K; value: SetStateAction<FinderState[K]> };
}[keyof FinderState];

const initialFinderState: FinderState = {
  open: false,
  query: "",
  mode: "all",
  respectGitignore: true,
  includeHidden: false,
  results: [],
  selectedIndex: 0,
  loading: false,
  filePreview: null,
  filePreviewLoading: false,
  filePreviewError: null,
  sessionMessages: null,
  sessionPreviewLoading: false,
};

function finderReducer(state: FinderState, action: FinderAction): FinderState {
  const prev = state[action.key];
  const next = typeof action.value === "function"
    ? (action.value as (p: typeof prev) => typeof prev)(prev)
    : action.value;
  return Object.is(next, prev) ? state : { ...state, [action.key]: next };
}

function useFinderSetters(dispatch: Dispatch<FinderAction>) {
  return useMemo(() => {
    const setter = <K extends keyof FinderState>(key: K): Dispatch<SetStateAction<FinderState[K]>> =>
      (value) => dispatch({ key, value } as FinderAction);
    return {
      setOpen: setter("open"),
      setQuery: setter("query"),
      setMode: setter("mode"),
      setRespectGitignore: setter("respectGitignore"),
      setIncludeHidden: setter("includeHidden"),
      setResults: setter("results"),
      setSelectedIndex: setter("selectedIndex"),
      setLoading: setter("loading"),
      setFilePreview: setter("filePreview"),
      setFilePreviewLoading: setter("filePreviewLoading"),
      setFilePreviewError: setter("filePreviewError"),
      setSessionMessages: setter("sessionMessages"),
      setSessionPreviewLoading: setter("sessionPreviewLoading"),
    };
  }, [dispatch]);
}

export function useFinderState() {
  const [state, dispatch] = useReducer(finderReducer, initialFinderState);
  const setters = useFinderSetters(dispatch);
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  return { ...state, ...setters, inputRef, resultsRef };
}
