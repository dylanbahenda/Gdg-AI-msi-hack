import { AlertNotification } from "../types/contracts";
import AlertCard from "./AlertCard";

interface Props {
  alerts: AlertNotification[];
  onCardClick: (a: AlertNotification) => void;
  showSpatial?: boolean;
}

export default function AlertFeed({ alerts, onCardClick, showSpatial = true }: Props) {
  if (alerts.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-[#6a6a6a] text-[13px] italic">
        Listening for events…
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {alerts.map((a, i) => (
        <AlertCard key={`${a.timestamp}-${i}`} alert={a} onClick={onCardClick} showSpatial={showSpatial} />
      ))}
    </div>
  );
}
