import { useState } from "react";

export function useOnChange<T>(value: T, onChange: () => void): void {
  const [prev, setPrev] = useState(value);
  if (!Object.is(prev, value)) {
    setPrev(value);
    onChange();
  }
}
