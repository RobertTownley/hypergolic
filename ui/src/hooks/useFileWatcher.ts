import { useEffect, useRef } from "react";
import { useAppSelector } from "@/store";
import { selectActiveSessionId } from "@/store/selectors";
import { subscribe, setWatchScope } from "@/api/fileWatcher";

export function useFileWatcher(onChange: () => void) {
  const ref = useRef(onChange);

  useEffect(() => { ref.current = onChange; });

  const activeSessionId = useAppSelector(selectActiveSessionId);

  useEffect(() => {
    setWatchScope({ sessionId: activeSessionId });
  }, [activeSessionId]);

  useEffect(() => {
    return subscribe(() => ref.current());
  }, []);
}
