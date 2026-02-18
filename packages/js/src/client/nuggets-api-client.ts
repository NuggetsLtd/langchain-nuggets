import type { NuggetsConfig, NuggetsAuthToken } from "../types.js";

export class NuggetsApiClientError extends Error {
  constructor(
    message: string,
    public code: string,
    public statusCode: number
  ) {
    super(message);
    this.name = "NuggetsApiClientError";
  }
}

export class NuggetsApiClient {
  private config: NuggetsConfig;
  private token: NuggetsAuthToken | null = null;

  constructor(config: NuggetsConfig) {
    this.config = config;
  }

  private async authenticate(): Promise<string> {
    if (this.token && this.token.expiresAt > Date.now()) {
      return this.token.accessToken;
    }

    const response = await fetch(`${this.config.apiUrl}/partner/auth`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        partnerId: this.config.partnerId,
        partnerSecret: this.config.partnerSecret,
      }),
    });

    if (!response.ok) {
      throw new NuggetsApiClientError(
        "Authentication failed",
        "AUTH_FAILED",
        response.status
      );
    }

    const data = await response.json();
    this.token = {
      accessToken: data.token,
      expiresAt: Date.now() + data.expiresIn * 1000,
    };

    return this.token.accessToken;
  }

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const token = await this.authenticate();

    const options: RequestInit = {
      method,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
    };

    if (body) {
      options.body = JSON.stringify(body);
    }

    const response = await fetch(`${this.config.apiUrl}${path}`, options);
    const data = await response.json();

    if (!response.ok) {
      throw new NuggetsApiClientError(
        data.message || "Request failed",
        data.code || "UNKNOWN",
        response.status
      );
    }

    return data as T;
  }

  async get<T>(path: string): Promise<T> {
    return this.request<T>("GET", path);
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>("POST", path, body);
  }
}
