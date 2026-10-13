declare module "citeproc" {
  interface Sys {
    retrieveLocale(lang: string): string;
    retrieveItem(id: string): Record<string, unknown>;
  }
  interface Engine {
    updateItems(ids: string[]): void;
    makeBibliography(): [Record<string, unknown>, string[]] | false;
  }
  const CSL: { Engine: new (sys: Sys, style: string, lang?: string, forceLang?: boolean) => Engine };
  export default CSL;
}
