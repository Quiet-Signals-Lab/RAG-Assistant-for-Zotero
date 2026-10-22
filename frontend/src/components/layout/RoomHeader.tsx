import React from "react";

const IS_MAC = typeof navigator !== "undefined" && /Mac/i.test(navigator.userAgent);

/**
 * The 44px bar across the top of every room: the room's own controls, then the
 * app name at the right beside the actions (the settings gear). The bar is the
 * window's drag region.
 */
const RoomHeader: React.FC<React.PropsWithChildren<{ title: string; className?: string; actions?: React.ReactNode }>> = ({ title, className, actions, children }) => (
  <header className={["room-header", IS_MAC ? "room-header--mac" : "", className ?? ""].filter(Boolean).join(" ")}>
    {children}
    <span className="room-brand__name">{title}</span>
    {actions}
  </header>
);

export default RoomHeader;
