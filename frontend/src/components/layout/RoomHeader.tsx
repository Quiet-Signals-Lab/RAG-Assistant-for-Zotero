import React from "react";

const IS_MAC = typeof navigator !== "undefined" && /Mac/i.test(navigator.userAgent);

/**
 * The 44px bar across the top of every room: brand mark and room name on the
 * left, the room's own controls after it. The bar is the window's drag region.
 */
const RoomHeader: React.FC<React.PropsWithChildren<{ title: string; className?: string }>> = ({ title, className, children }) => (
  <header className={["room-header", IS_MAC ? "room-header--mac" : "", className ?? ""].filter(Boolean).join(" ")}>
    <div className="room-brand">
      <span className="room-brand__mark" aria-hidden="true" />
      <span className="room-brand__name">{title}</span>
    </div>
    {children}
  </header>
);

export default RoomHeader;
