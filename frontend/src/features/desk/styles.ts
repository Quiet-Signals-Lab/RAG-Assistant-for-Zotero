/** The CSL styles shipped with the app (CC BY-SA 3.0, from the CSL project) and the en-US locale. */
import apa from "../../assets/csl/apa.csl?raw";
import chicagoAuthorDate from "../../assets/csl/chicago-author-date.csl?raw";
import chicagoNotes from "../../assets/csl/chicago-notes-bibliography.csl?raw";
import localeEnUS from "../../assets/csl/locales-en-US.xml?raw";

export const LOCALE_EN_US = localeEnUS;

export const BUNDLED_STYLES: { id: string; title: string; xml: string }[] = [
  { id: "apa", title: "APA 7th", xml: apa },
  { id: "chicago-author-date", title: "Chicago 18th (author-date)", xml: chicagoAuthorDate },
  { id: "chicago-notes-bibliography", title: "Chicago 18th (notes and bibliography)", xml: chicagoNotes },
];
