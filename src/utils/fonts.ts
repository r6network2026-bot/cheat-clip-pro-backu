export const getFontFaceSource = (url: string, baseUrl: string): string =>
  `url("${new URL(url, baseUrl).href}")`;
