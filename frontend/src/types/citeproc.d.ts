declare module "citeproc" {
  interface Sys {
    retrieveLocale(lang: string): string;
    retrieveItem(id: string): Record<string, unknown>;
  }
  class Engine {
    constructor(sys: Sys, style: string, lang?: string, forceLang?: boolean);
    updateItems(ids: string[]): void;
    makeBibliography(): [Record<string, unknown>, string[]] | false;
  }
  const CSL: { Engine: typeof Engine };
  export default CSL;
}
