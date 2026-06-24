import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { 
  Plus, 
  ShoppingBag, 
  Eye, 
  Archive, 
  Trash2, 
  CheckCircle, 
  Search,
  Filter,
  TrendingUp,
  DollarSign,
  Users,
  Activity,
  ArrowUpRight
} from "lucide-react";
import { funnelApi, type DigitalProduct, type FunnelAnalyticsSummary } from "../../api/funnel";
import { useAuth } from "../../contexts/AuthContext";

export default function ProductList() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [products, setProducts] = useState<DigitalProduct[]>([]);
  const [analytics, setAnalytics] = useState<FunnelAnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const organizationId = user?.organization_id || "";

  useEffect(() => {
    fetchData();
  }, [includeArchived]);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [prodsData, statsData] = await Promise.all([
        funnelApi.listProducts({ include_archived: includeArchived }),
        funnelApi.getAnalyticsSummary().catch(() => null)
      ]);
      setProducts(prodsData);
      if (statsData) {
        setAnalytics(statsData);
      }
    } catch (err) {
      console.error("Failed to load products/analytics data", err);
    } finally {
      setLoading(false);
    }
  };

  const handlePublish = async (id: string) => {
    if (!confirm("Are you sure you want to publish this product? This will make the product live.")) return;
    try {
      await funnelApi.publishProduct(id);
      await fetchData();
    } catch (err) {
      alert("Failed to publish product. Ensure it has a valid slug and at least one active delivery asset.");
    }
  };

  const handleArchive = async (id: string) => {
    if (!confirm("Archive this product? It will no longer accept new checkouts.")) return;
    try {
      await funnelApi.archiveProduct(id);
      await fetchData();
    } catch (err) {
      alert("Failed to archive product.");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Are you sure you want to delete this product? This cannot be undone.")) return;
    try {
      await funnelApi.deleteProduct(id);
      await fetchData();
    } catch (err) {
      alert("Failed to delete product.");
    }
  };

  const filteredProducts = products.filter(product => {
    const matchesSearch = product.name.toLowerCase().includes(searchTerm.toLowerCase()) || 
                          product.slug.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = statusFilter === "all" || product.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
            <ShoppingBag className="text-indigo-400 w-7 h-7" />
            Digital Product Funnels
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Manage your digital products, configure Stripe checkouts, deliver secure assets, and monitor conversion metrics.
          </p>
        </div>
        <Link 
          to="/products/new"
          className="flex items-center justify-center gap-2 px-4 py-2.5 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white font-medium rounded-xl shadow-lg transition-all transform hover:-translate-y-0.5 duration-150"
        >
          <Plus size={18} />
          Create Product
        </Link>
      </div>

      {/* Analytics Summary Panels */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-5 hover:border-slate-700/50 transition-all">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs text-slate-400 uppercase tracking-wider font-semibold">Total Revenue</p>
              <h3 className="text-2xl font-bold text-slate-100 mt-2">
                {analytics ? `${analytics.total_revenue.toLocaleString()} THB` : "0.00 THB"}
              </h3>
              <p className="text-xs text-slate-500 mt-1">From secure Stripe payments</p>
            </div>
            <div className="p-3 bg-emerald-500/10 rounded-xl text-emerald-400">
              <DollarSign size={20} />
            </div>
          </div>
        </div>

        <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-5 hover:border-slate-700/50 transition-all">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs text-slate-400 uppercase tracking-wider font-semibold">Total Purchases</p>
              <h3 className="text-2xl font-bold text-slate-100 mt-2">
                {analytics ? analytics.purchases.toLocaleString() : "0"}
              </h3>
              <p className="text-xs text-slate-500 mt-1">
                AOV: {analytics ? `${analytics.average_order_value.toFixed(2)} THB` : "0 THB"}
              </p>
            </div>
            <div className="p-3 bg-indigo-500/10 rounded-xl text-indigo-400">
              <TrendingUp size={20} />
            </div>
          </div>
        </div>

        <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-5 hover:border-slate-700/50 transition-all">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs text-slate-400 uppercase tracking-wider font-semibold">Funnel Leads</p>
              <h3 className="text-2xl font-bold text-slate-100 mt-2">
                {analytics ? analytics.leads.toLocaleString() : "0"}
              </h3>
              <p className="text-xs text-slate-500 mt-1">
                Opt-in rate: {analytics ? `${analytics.lead_conversion_rate.toFixed(1)}%` : "0.0%"}
              </p>
            </div>
            <div className="p-3 bg-purple-500/10 rounded-xl text-purple-400">
              <Users size={20} />
            </div>
          </div>
        </div>

        <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-5 hover:border-slate-700/50 transition-all">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs text-slate-400 uppercase tracking-wider font-semibold">Purchase Conv. Rate</p>
              <h3 className="text-2xl font-bold text-slate-100 mt-2">
                {analytics ? `${analytics.purchase_conversion_rate.toFixed(2)}%` : "0.00%"}
              </h3>
              <p className="text-xs text-slate-500 mt-1">
                Checkout conversion: {analytics ? `${analytics.checkout_to_purchase_rate.toFixed(1)}%` : "0.0%"}
              </p>
            </div>
            <div className="p-3 bg-cyan-500/10 rounded-xl text-cyan-400">
              <Activity size={20} />
            </div>
          </div>
        </div>
      </div>

      {/* Product List Panel */}
      <div className="bg-slate-900/40 border border-slate-800/80 rounded-3xl shadow-xl overflow-hidden backdrop-blur-xl">
        {/* Table Filters */}
        <div className="p-6 border-b border-slate-850 flex flex-col sm:flex-row gap-4 items-center justify-between">
          <div className="relative w-full sm:w-80">
            <Search className="absolute left-3.5 top-3 text-slate-500 w-4 h-4" />
            <input
              type="text"
              placeholder="Search products or slugs..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-slate-950/60 border border-slate-800 focus:border-indigo-500 text-slate-200 pl-10 pr-4 py-2 rounded-xl text-sm outline-none transition-colors"
            />
          </div>

          <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto justify-end">
            <div className="flex items-center gap-2">
              <Filter className="text-slate-500 w-4 h-4" />
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="bg-slate-950/60 border border-slate-800 focus:border-indigo-500 text-slate-300 px-3.5 py-2 rounded-xl text-xs outline-none transition-colors"
              >
                <option value="all">All Statuses</option>
                <option value="draft">Draft</option>
                <option value="published">Published</option>
                <option value="archived">Archived</option>
              </select>
            </div>

            <label className="flex items-center gap-2.5 text-xs text-slate-400 cursor-pointer select-none border border-slate-800 bg-slate-950/30 px-3.5 py-2 rounded-xl hover:bg-slate-950/60 transition-colors">
              <input
                type="checkbox"
                checked={includeArchived}
                onChange={(e) => setIncludeArchived(e.target.checked)}
                className="rounded border-slate-800 text-indigo-500 focus:ring-0 focus:ring-offset-0 bg-slate-950"
              />
              Show Archived
            </label>
          </div>
        </div>

        {/* Table content */}
        {loading ? (
          <div className="p-20 text-center text-slate-400">
            <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            Loading catalog products...
          </div>
        ) : filteredProducts.length === 0 ? (
          <div className="p-20 text-center">
            <div className="w-12 h-12 bg-slate-800/50 rounded-2xl flex items-center justify-center mx-auto mb-4 text-slate-500">
              <ShoppingBag size={24} />
            </div>
            <h3 className="text-lg font-bold text-slate-200">No products found</h3>
            <p className="text-sm text-slate-500 max-w-sm mx-auto mt-1">
              Create your first digital product funnel to start collecting leads and selling products.
            </p>
            <Link
              to="/products/new"
              className="inline-flex items-center gap-2 mt-4 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium rounded-xl transition-all"
            >
              <Plus size={16} />
              Create Product
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-850 text-slate-400 text-xs font-semibold uppercase tracking-wider bg-slate-950/20">
                  <th className="px-6 py-4">Product Details</th>
                  <th className="px-6 py-4">Slug / Landing URL</th>
                  <th className="px-6 py-4">Status</th>
                  <th className="px-6 py-4">Price</th>
                  <th className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-850/50">
                {filteredProducts.map((product) => {
                  const isPublished = product.status === "published";
                  const isDraft = product.status === "draft";

                  return (
                    <tr key={product.id} className="hover:bg-slate-950/15 transition-colors">
                      <td className="px-6 py-5">
                        <div className="flex items-center gap-3">
                          {product.cover_image_url ? (
                            <img
                              src={product.cover_image_url}
                              alt={product.name}
                              className="w-10 h-10 object-cover rounded-lg border border-slate-800"
                            />
                          ) : (
                            <div className="w-10 h-10 bg-slate-800/80 rounded-lg flex items-center justify-center text-slate-400">
                              <ShoppingBag size={18} />
                            </div>
                          )}
                          <div>
                            <div className="font-semibold text-slate-200 text-sm hover:text-indigo-400 transition-colors">
                              <Link to={`/products/${product.id}`}>{product.name}</Link>
                            </div>
                            <div className="text-xs text-slate-400 mt-0.5 line-clamp-1 max-w-xs">
                              {product.short_description || "No description provided"}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-5">
                        <div className="flex items-center gap-1.5">
                          <code className="text-xs text-indigo-300 font-mono bg-indigo-500/5 px-2 py-0.5 rounded border border-indigo-500/10">
                            {product.slug}
                          </code>
                          {isPublished && (
                            <a
                              href={`/f/${organizationId}/${product.slug}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-slate-400 hover:text-slate-200"
                              title="View Sales Page"
                            >
                              <ArrowUpRight size={14} />
                            </a>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-5">
                        <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold tracking-wide uppercase border ${
                          isPublished 
                            ? "bg-emerald-500/5 text-emerald-400 border-emerald-500/10" 
                            : isDraft 
                              ? "bg-amber-500/5 text-amber-400 border-amber-500/10"
                              : "bg-slate-800/50 text-slate-400 border-slate-700/50"
                        }`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${
                            isPublished ? "bg-emerald-400 animate-pulse" : isDraft ? "bg-amber-400" : "bg-slate-500"
                          }`} />
                          {product.status}
                        </span>
                      </td>
                      <td className="px-6 py-5 font-semibold text-slate-200 text-sm">
                        {parseFloat(product.price_amount.toString()).toFixed(2)} {product.currency}
                      </td>
                      <td className="px-6 py-5 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => navigate(`/products/${product.id}`)}
                            className="p-1.5 bg-slate-800 hover:bg-slate-750 hover:text-slate-200 text-slate-400 rounded-lg transition-all"
                            title="Edit Product"
                          >
                            <Eye size={14} />
                          </button>

                          {isDraft && (
                            <button
                              onClick={() => handlePublish(product.id)}
                              className="p-1.5 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 rounded-lg transition-all"
                              title="Publish Product"
                            >
                              <CheckCircle size={14} />
                            </button>
                          )}

                          {isPublished && (
                            <button
                              onClick={() => handleArchive(product.id)}
                              className="p-1.5 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 rounded-lg transition-all"
                              title="Archive Product"
                            >
                              <Archive size={14} />
                            </button>
                          )}

                          <button
                            onClick={() => handleDelete(product.id)}
                            className="p-1.5 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 rounded-lg transition-all"
                            title="Delete Product"
                          >
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
