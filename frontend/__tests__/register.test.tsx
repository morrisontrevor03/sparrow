import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const replace = jest.fn();
jest.mock("next/navigation", () => ({ useRouter: () => ({ replace: mockReplace() }) }));
function mockReplace() {
  return replace;
}

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("@/lib/auth", () => ({ useAuth: () => ({ login: jest.fn() }) }));
jest.mock("@/lib/posthog", () => ({ track: jest.fn() }));
jest.mock("@/lib/api", () => ({ auth: { register: jest.fn() } }));

import { auth } from "@/lib/api";
import RegisterPage from "@/app/(auth)/register/page";

const mockedRegister = auth.register as jest.Mock;

describe("RegisterPage", () => {
  beforeEach(() => jest.clearAllMocks());

  it("renders the signup fields", () => {
    render(<RegisterPage />);
    expect(screen.getByPlaceholderText("you@example.com")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("At least 8 characters")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create account/i })).toBeInTheDocument();
  });

  it("offers Google signup", () => {
    render(<RegisterPage />);
    expect(screen.getByText(/sign up with google/i)).toBeInTheDocument();
  });

  it("links to the login page", () => {
    render(<RegisterPage />);
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute("href", "/login");
  });

  it("states the free credit grant", () => {
    render(<RegisterPage />);
    expect(screen.getByText(/25 free credits/i)).toBeInTheDocument();
  });

  it("registers and sends the user to onboarding", async () => {
    const user = userEvent.setup();
    mockedRegister.mockResolvedValue({ access_token: "token-123" });

    render(<RegisterPage />);
    await user.type(screen.getByPlaceholderText("Jordan Blake"), "Ada Lovelace");
    await user.type(screen.getByPlaceholderText("you@example.com"), "ada@example.com");
    await user.type(screen.getByPlaceholderText("At least 8 characters"), "password123");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() =>
      expect(mockedRegister).toHaveBeenCalledWith(
        "ada@example.com",
        "password123",
        "Ada Lovelace"
      )
    );
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/onboarding"));
  });
});
