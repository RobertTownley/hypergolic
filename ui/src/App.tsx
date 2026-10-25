import { Provider } from "react-redux";
import { store } from "@/store";
import { WebSocketProvider } from "@/api/WebSocketProvider";
import { AppFrame } from "@/layout/AppFrame";

export function App() {
  return (
    <Provider store={store}>
      <WebSocketProvider>
        <AppFrame />
      </WebSocketProvider>
    </Provider>
  );
}
