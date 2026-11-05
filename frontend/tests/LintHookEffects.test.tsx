import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LanguageProvider, useLang } from "@/i18n/LanguageContext";
import ApprovalDetailPage from "@/pages/admin/ApprovalDetail";
import TokenROIPage from "@/pages/admin/TokenROI";
import DeliveryAccessPage from "@/pages/funnel/DeliveryAccessPage";
import ProductList from "@/pages/funnel/ProductList";

const { mockAdminApi, mockFunnelApi, mockUseAuth } = vi.hoisted(() => ({
  mockAdminApi: {
    getApprovalById: vi.fn(),
    approveApproval: vi.fn(),
    rejectApproval: vi.fn(),
    getTokenRoiSummary: vi.fn(),
  },
  mockFunnelApi: {
    getDeliveryPayload: vi.fn(),
    consumeDeliveryPayload: vi.fn(),
    listProducts: vi.fn(),
    getAnalyticsSummary: vi.fn(),
  },
  mockUseAuth: vi.fn(),
}));

vi.mock("@/lib/admin-api", () => mockAdminApi);
vi.mock("@/api/funnel", () => ({ funnelApi: mockFunnelApi }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => mockUseAuth() }));

function NavigationButton({ label, to }: { label: string; to: string }) {
  const navigate = useNavigate();

  return (
    <button type="button" onClick={() => navigate(to)}>
      {label}
    </button>
  );
}

function LanguageToggle() {
  const { toggle } = useLang();

  return (
    <button type="button" onClick={toggle}>
      Toggle language
    </button>
  );
}

function renderWithRouter(initialEntry: string, children: ReactNode) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>{children}</MemoryRouter>,
  );
}

describe("page effect request triggers", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();

    mockAdminApi.getApprovalById.mockImplementation(async (id: string) => ({
      id,
      title: "Approval " + id,
      action_type: "draft_review",
      subject_type: null,
      subject_id: null,
      status: "pending",
      policy_class: "high_impact_external",
      requested_by: "drafter",
      details: null,
      preview: null,
      expires_at: null,
      resolved_at: null,
      resolution_note: null,
      created_at: null,
    }));
    mockAdminApi.approveApproval.mockResolvedValue(true);
    mockAdminApi.rejectApproval.mockResolvedValue(true);
    mockAdminApi.getTokenRoiSummary.mockResolvedValue({
      profitable: true,
      recommendation: "Keep current policy",
      tokens_saved: 2500,
    });

    mockFunnelApi.getDeliveryPayload.mockImplementation(async (token: string) => ({
      product_name: "Product " + token,
      asset_title: "Quick-start guide",
      asset_type: "text",
      content_body: "Delivery content",
    }));
    mockFunnelApi.consumeDeliveryPayload.mockResolvedValue({});
    mockFunnelApi.listProducts.mockResolvedValue([]);
    mockFunnelApi.getAnalyticsSummary.mockResolvedValue(null);
    mockUseAuth.mockReturnValue({ user: { organization_id: "org-test" } });
  });

  it("reloads approval details once when the route ID changes", async () => {
    renderWithRouter(
      "/admin/approvals/first",
      <>
        <NavigationButton label="Next approval" to="/admin/approvals/second" />
        <Routes>
          <Route path="/admin/approvals/:id" element={<ApprovalDetailPage />} />
        </Routes>
      </>,
    );

    expect(await screen.findByText("Approval first")).toBeInTheDocument();
    expect(mockAdminApi.getApprovalById).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Next approval" }));

    expect(await screen.findByText("Approval second")).toBeInTheDocument();
    expect(mockAdminApi.getApprovalById).toHaveBeenNthCalledWith(2, "second");
    expect(mockAdminApi.getApprovalById).toHaveBeenCalledTimes(2);
  });

  it("reloads a delivery token once when the route token changes, not on locale change", async () => {
    renderWithRouter(
      "/delivery/first",
      <LanguageProvider>
        <LanguageToggle />
        <NavigationButton label="Next token" to="/delivery/second" />
        <Routes>
          <Route path="/delivery/:token" element={<DeliveryAccessPage />} />
        </Routes>
      </LanguageProvider>,
    );

    expect(await screen.findByText("Product first")).toBeInTheDocument();
    expect(mockFunnelApi.getDeliveryPayload).toHaveBeenCalledTimes(1);
    expect(mockFunnelApi.getDeliveryPayload).toHaveBeenLastCalledWith("first");

    fireEvent.click(screen.getByRole("button", { name: "Next token" }));

    expect(await screen.findByText("Product second")).toBeInTheDocument();
    expect(mockFunnelApi.getDeliveryPayload).toHaveBeenCalledTimes(2);
    expect(mockFunnelApi.getDeliveryPayload).toHaveBeenLastCalledWith("second");

    fireEvent.click(screen.getByRole("button", { name: "Toggle language" }));

    expect(mockFunnelApi.getDeliveryPayload).toHaveBeenCalledTimes(2);
  });

  it("reloads products for the archive filter but not local search or status edits", async () => {
    renderWithRouter(
      "/products",
      <Routes>
        <Route path="/products" element={<ProductList />} />
      </Routes>,
    );

    await waitFor(() => expect(mockFunnelApi.listProducts).toHaveBeenCalledTimes(1));
    expect(mockFunnelApi.listProducts).toHaveBeenLastCalledWith({
      include_archived: false,
    });

    fireEvent.change(screen.getByPlaceholderText("Search products or slugs..."), {
      target: { value: "guide" },
    });
    fireEvent.change(screen.getByRole("combobox"), {
      target: { value: "published" },
    });

    expect(mockFunnelApi.listProducts).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("checkbox", { name: "Show Archived" }));

    await waitFor(() => expect(mockFunnelApi.listProducts).toHaveBeenCalledTimes(2));
    expect(mockFunnelApi.listProducts).toHaveBeenLastCalledWith({
      include_archived: true,
    });
  });

  it("loads the default ROI once and evaluates the latest edited inputs on demand", async () => {
    renderWithRouter(
      "/admin/token-roi",
      <TokenROIPage />,
    );

    await waitFor(() =>
      expect(mockAdminApi.getTokenRoiSummary).toHaveBeenCalledTimes(1),
    );
    expect(mockAdminApi.getTokenRoiSummary).toHaveBeenCalledWith(
      expect.objectContaining({ tokens_saved: 2500 }),
    );

    fireEvent.change(screen.getByDisplayValue("2500"), {
      target: { value: "3200" },
    });
    expect(mockAdminApi.getTokenRoiSummary).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Evaluate" }));

    await waitFor(() =>
      expect(mockAdminApi.getTokenRoiSummary).toHaveBeenCalledTimes(2),
    );
    expect(mockAdminApi.getTokenRoiSummary).toHaveBeenLastCalledWith(
      expect.objectContaining({ tokens_saved: 3200 }),
    );
  });
});
