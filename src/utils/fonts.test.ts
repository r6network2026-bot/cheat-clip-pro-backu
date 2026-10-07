import { describe, expect, it } from 'vitest';
import { getFontFaceSource } from './fonts';

describe('getFontFaceSource', () => {
  it('quotes font URLs containing spaces and resolves them against the app origin', () => {
    expect(getFontFaceSource('/api/font-file/Bebas Neue.ttf', 'http://localhost:5173/'))
      .toBe('url("http://localhost:5173/api/font-file/Bebas%20Neue.ttf")');
  });

  it('preserves an absolute font URL while making it CSS-safe', () => {
    expect(getFontFaceSource('https://cdn.example.test/my font.ttf', 'http://localhost/'))
      .toBe('url("https://cdn.example.test/my%20font.ttf")');
  });
});
