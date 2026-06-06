import { LiteratureStreamProvider } from "@/contexts/LiteratureStreamContext";
import { LitPilotChatPage } from "@/integrations/meso/LitPilotChatPage";

export default function ChatPage() {
  return (
    <LiteratureStreamProvider>
      <LitPilotChatPage />
    </LiteratureStreamProvider>
  );
}
