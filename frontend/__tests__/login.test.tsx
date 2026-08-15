import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const replace = jest.fn();
jest.mock("next/navigation", () => ({ useRouter: () => ({ replace: mockReplace() }) }));
// The factory cannot close over `replace` directly (jest hoists it above the
// declaration), so route it through a getter that resolves lazily.
function mockReplace() {
  return replace;
}

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("@/lib/auth", () => ({ useAuth: () => ({ login: jest.fn() }) }));
jest.mock("@/lib/api", () => ({ auth: { login: jest.fn() } }));

import { auth } from "@/lib/api";
import LoginPage from "@/app/(auth)/login/page";

const mockedLogin = auth.login as jest.Mock;

describe("LoginPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    window.history.replaceState({}, "", "/login");
  });

  it("renders the email and password fields", () => {
    render(<LoginPage />);
    expect(screen.getByPlaceholderText("you@example.com")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("••••••••")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("offers Google sign-in", () => {
    render(<LoginPage />);
    expect(screen.getByText(/continue with google/i)).toBeInTheDocument();
  });

  it("links to the register page", () => {
    render(<LoginPage />);
    expect(screen.getByRole("link", { name: /sign up/i })).toHaveAttribute("href", "/register");
  });

  it("submits credentials and redirects to the dashboard", async () => {
    const user = userEvent.setup();
    mockedLogin.mockResolvedValue({ access_token: "token-123" });

    render(<LoginPage />);
    await user.type(screen.getByPlaceholderText("you@example.com"), "a@b.com");
    await user.type(screen.getByPlaceholderText("••••••••"), "password123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(mockedLogin).toHaveBeenCalledWith("a@b.com", "password123"));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
  });

  it("returns to an in-flight MCP consent flow instead of the dashboard", async () => {
    // A user who hits /oauth/consent unauthenticated is bounced here with
    // ?next=; dropping it would strand the MCP client mid-authorization.
    window.history.replaceState({}, "", "/login?next=%2Foauth%2Fconsent%3Fclient_id%3Dabc");
    const user = userEvent.setup();
    mockedLogin.mockResolvedValue({ access_token: "token-123" });

    render(<LoginPage />);
    await user.type(screen.getByPlaceholderText("you@example.com"), "a@b.com");
    await user.type(screen.getByPlaceholderText("••••••••"), "password123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith("/oauth/consent?client_id=abc")
    );
  });

  it("does not follow an absolute next URL", async () => {
    window.history.replaceState({}, "", "/login?next=https%3A%2F%2Fevil.example.com");
    const user = userEvent.setup();
    mockedLogin.mockResolvedValue({ access_token: "token-123" });

    render(<LoginPage />);
    await user.type(screen.getByPlaceholderText("you@example.com"), "a@b.com");
    await user.type(screen.getByPlaceholderText("••••••••"), "password123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
  });
});
