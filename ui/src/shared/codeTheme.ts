import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

export const codeTheme = {
  ...oneDark,
  'pre[class*="language-"]': {
    ...oneDark['pre[class*="language-"]'],
    background: "#0a0a0f",
  },
  'code[class*="language-"]': {
    ...oneDark['code[class*="language-"]'],
    background: "none",
  },
};
