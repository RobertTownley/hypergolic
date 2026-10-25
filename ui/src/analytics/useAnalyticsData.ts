import { useCallback, useEffect, useMemo } from "react";
import { useAppDispatch, useAppSelector } from "@/store";
import {
  loadAnalytics,
  setProjectId as setProjectIdAction,
  setDays as setDaysAction,
  selectAnalyticsProjectId,
  selectAnalyticsDays,
} from "@/store/analyticsSlice";

export function useAnalyticsData() {
  const dispatch = useAppDispatch();
  const projectIds = useAppSelector((s) => s.projects.ids);
  const projectEntities = useAppSelector((s) => s.projects.entities);
  const { loading, error, summary, timeseries, tools } = useAppSelector((s) => s.analytics);

  // Params live in the slice next to the results they describe, so a
  // remount (e.g. switching tabs away and back) doesn't reset them while
  // the slice still holds the previous query's data.
  const projectId = useAppSelector(selectAnalyticsProjectId);
  const days = useAppSelector(selectAnalyticsDays);

  const setProjectId = useCallback(
    (id: string | undefined) => {
      dispatch(setProjectIdAction(id));
    },
    [dispatch],
  );

  const setDays = useCallback(
    (d: number) => {
      dispatch(setDaysAction(d));
    },
    [dispatch],
  );

  // Refetch on param change; the thunk's condition skips the dispatch when
  // the slice already holds (or is fetching) data for these exact params.
  useEffect(() => {
    dispatch(loadAnalytics({ projectId, days }));
  }, [dispatch, projectId, days]);

  const projectOptions = useMemo(
    () => [
      { label: "All Projects", value: "" },
      ...projectIds.map((id: string) => ({
        label: projectEntities[id]?.name ?? id,
        value: id,
      })),
    ],
    [projectIds, projectEntities],
  );

  return { projectId, setProjectId, days, setDays, loading, error, summary, timeseries, tools, projectOptions };
}
