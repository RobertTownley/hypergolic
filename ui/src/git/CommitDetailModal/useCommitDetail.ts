import { useCallback } from "react";
import { useAppDispatch, useAppSelector } from "@/store";
import { clearCommitDetail } from "@/store/workspaceSlice";
import { selectCommitDetail, selectCommitDetailLoading } from "@/store/selectors";
import { parseDiff } from "@/shared/diff";

export function useCommitDetail() {
  const dispatch = useAppDispatch();
  const commitDetail = useAppSelector(selectCommitDetail);
  const commitDetailLoading = useAppSelector(selectCommitDetailLoading);

  const onClose = useCallback(() => dispatch(clearCommitDetail()), [dispatch]);

  const isOpen = !!(commitDetail || commitDetailLoading);
  const diffLines = commitDetail?.diff ? parseDiff(commitDetail.diff, { fileHeaders: true }) : [];

  return { commitDetail, commitDetailLoading, isOpen, diffLines, onClose };
}
