export function scrollerAbove(target: EventTarget | null, root: HTMLElement): boolean {
  for (let n = target instanceof Element ? target : null; n && n !== root; n = n.parentElement) {
    if (n.scrollTop > 0) return true;
  }
  return false;
}
