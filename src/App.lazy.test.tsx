import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { LanguageProvider } from './locales';

vi.mock('./utils/api', () => ({
  resilientFetch: vi.fn(async () => ({
    ok: true,
    json: async () => ({ exists: false, size: 0, sample_lines: [] }),
  })),
}));

describe('App lazy-loaded features', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ user: { id: 'test-user', email: 'test@example.com', display_name: 'Test User' } }),
    })));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('loads the Cookies modal only after the user opens it', async () => {
    const existingScript = document.createElement('script');
    document.head.appendChild(existingScript);

    render(
      <LanguageProvider>
        <App />
      </LanguageProvider>,
    );

    expect(document.querySelector('.cookies-modal-card')).toBeNull();
    fireEvent.click(await screen.findByRole('button', { name: /cookies/i }));

    await waitFor(() => {
      expect(document.querySelector('.cookies-modal-card')).not.toBeNull();
    });
  });
});
