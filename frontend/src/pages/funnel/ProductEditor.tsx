import { useEffect, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { 
  ArrowLeft, 
  Save, 
  Trash2, 
  Plus, 
  FileText, 
  Link as LinkIcon, 
  Check, 
  AlertTriangle,
  File,
  Lock,
  Globe,
  Settings,
  Archive,
  BookOpen
} from "lucide-react";
import { funnelApi, type DigitalProduct, type DeliveryAsset } from "../../api/funnel";

export default function ProductEditor() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isNew = !id || id === "new";

  // Product Form State
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [shortDescription, setShortDescription] = useState("");
  const [productType, setProductType] = useState("other");
  const [priceAmount, setPriceAmount] = useState<number | string>(0);
  const [currency, setCurrency] = useState("THB");
  const [coverImageUrl, setCoverImageUrl] = useState("");
  const [salesPageContent, setSalesPageContent] = useState("");
  const [status, setStatus] = useState("draft");

  // Assets Panel State
  const [assets, setAssets] = useState<DeliveryAsset[]>([]);
  const [showAssetModal, setShowAssetModal] = useState(false);
  const [assetTitle, setAssetTitle] = useState("");
  const [assetType, setAssetType] = useState("pdf");
  const [assetDesc, setAssetDesc] = useState("");
  const [assetStorage, setAssetStorage] = useState("");
  const [assetUrl, setAssetUrl] = useState("");
  const [assetBody, setAssetBody] = useState("");

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    if (!isNew && id) {
      loadProductAndAssets(id);
    }
  }, [id]);

  const loadProductAndAssets = async (productId: string) => {
    try {
      setLoading(true);
      const prod = await funnelApi.getProduct(productId);
      setName(prod.name);
      setSlug(prod.slug);
      setDescription(prod.description || "");
      setShortDescription(prod.short_description || "");
      setProductType(prod.product_type);
      setPriceAmount(prod.price_amount);
      setCurrency(prod.currency);
      setCoverImageUrl(prod.cover_image_url || "");
      setSalesPageContent(prod.sales_page_content || "");
      setStatus(prod.status);

      const assetsData = await funnelApi.listAssets(productId);
      setAssets(assetsData);
    } catch (err) {
      console.error("Failed to load product details", err);
      setErrorMsg("Failed to retrieve product details from database.");
    } finally {
      setLoading(false);
    }
  };

  const handleSaveProduct = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !slug.trim()) {
      setErrorMsg("Product name and unique slug are required fields.");
      return;
    }

    try {
      setSaving(true);
      setErrorMsg("");
      const payload: Partial<DigitalProduct> = {
        name,
        slug: slug.trim().toLowerCase().replace(/[^a-z0-9-_]/g, "-"),
        description,
        short_description: shortDescription,
        product_type: productType,
        price_amount: parseFloat(priceAmount.toString()) || 0,
        currency,
        cover_image_url: coverImageUrl || undefined,
        sales_page_content: salesPageContent || undefined
      };

      if (isNew) {
        const newProduct = await funnelApi.createProduct(payload);
        navigate(`/products/${newProduct.id}`);
      } else if (id) {
        await funnelApi.updateProduct(id, payload);
        alert("Product saved successfully!");
      }
    } catch (err: any) {
      console.error("Save product failed", err);
      setErrorMsg(err.response?.data?.detail || "An error occurred while saving the product.");
    } finally {
      setSaving(false);
    }
  };

  const handleAddAsset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!id || isNew) return;
    if (!assetTitle.trim()) {
      alert("Asset title is required.");
      return;
    }

    try {
      const payload: Partial<DeliveryAsset> = {
        title: assetTitle,
        asset_type: assetType,
        description: assetDesc || undefined,
        storage_path: assetStorage || undefined,
        external_url: assetUrl || undefined,
        content_body: assetBody || undefined,
        is_active: true
      };

      await funnelApi.createAsset(id, payload);
      setShowAssetModal(false);
      
      // Clear inputs
      setAssetTitle("");
      setAssetDesc("");
      setAssetStorage("");
      setAssetUrl("");
      setAssetBody("");

      // Reload
      const assetsData = await funnelApi.listAssets(id);
      setAssets(assetsData);
    } catch (err) {
      console.error("Add asset failed", err);
      alert("Failed to add delivery asset.");
    }
  };

  const handleDeactivateAsset = async (assetId: string) => {
    if (!confirm("Are you sure you want to deactivate this asset? Disabled assets are omitted from customer downloads.")) return;
    try {
      await funnelApi.deactivateAsset(assetId);
      if (id) {
        const assetsData = await funnelApi.listAssets(id);
        setAssets(assetsData);
      }
    } catch (err) {
      console.error("Deactivate asset failed", err);
      alert("Failed to deactivate asset.");
    }
  };

  if (loading) {
    return (
      <div className="p-20 text-center text-slate-400">
        <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
        Retrieving funnel records...
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Top Navigation */}
      <div className="flex items-center justify-between">
        <Link 
          to="/products"
          className="flex items-center gap-2 text-slate-400 hover:text-slate-200 text-sm font-medium transition-colors"
        >
          <ArrowLeft size={16} />
          Back to Products
        </Link>
        {!isNew && (
          <div className="flex items-center gap-2">
            <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold tracking-wide uppercase border ${
              status === "published" 
                ? "bg-emerald-500/5 text-emerald-400 border-emerald-500/10" 
                : status === "draft" 
                  ? "bg-amber-500/5 text-amber-400 border-amber-500/10"
                  : "bg-slate-800/50 text-slate-400 border-slate-700/50"
            }`}>
              <span className={`w-1.5 h-1.5 rounded-full ${
                status === "published" ? "bg-emerald-400 animate-pulse" : status === "draft" ? "bg-amber-400" : "bg-slate-500"
              }`} />
              {status}
            </span>
          </div>
        )}
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left Form (2 Columns) */}
        <div className="lg:col-span-2 space-y-6">
          <form onSubmit={handleSaveProduct} className="bg-slate-900/40 border border-slate-800 rounded-3xl p-6 space-y-6 shadow-xl backdrop-blur-xl">
            <div className="border-b border-slate-850 pb-4">
              <h2 className="text-lg font-bold text-slate-100">
                {isNew ? "Create Digital Product Funnel" : "Edit Digital Product Details"}
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                Configure your product page metadata, landing visual assets, pricing structures, and product information.
              </p>
            </div>

            {errorMsg && (
              <div className="p-4 bg-rose-500/10 border border-rose-500/20 text-rose-400 text-sm rounded-2xl flex items-start gap-3">
                <AlertTriangle size={18} className="mt-0.5 shrink-0" />
                <p>{errorMsg}</p>
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-xs font-semibold text-slate-300">Product Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. 2026 Ultimate Efficiency E-Book"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    if (isNew) {
                      // Generate slug
                      setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9\s]/g, "").replace(/\s+/g, "-"));
                    }
                  }}
                  className="w-full bg-slate-950/60 border border-slate-800 focus:border-indigo-500 text-slate-200 px-4 py-2.5 rounded-xl text-sm outline-none transition-colors"
                />
              </div>

              <div className="space-y-2">
                <label className="text-xs font-semibold text-slate-300">Unique URL Slug *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. ultimate-efficiency-2026"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  className="w-full bg-slate-950/60 border border-slate-800 focus:border-indigo-500 text-slate-200 px-4 py-2.5 rounded-xl text-sm outline-none transition-colors"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <label className="text-xs font-semibold text-slate-300">Product Type</label>
                <select
                  value={productType}
                  onChange={(e) => setProductType(e.target.value)}
                  className="w-full bg-slate-950/60 border border-slate-800 focus:border-indigo-500 text-slate-300 px-4 py-2.5 rounded-xl text-sm outline-none transition-colors"
                >
                  <option value="ebook">E-Book</option>
                  <option value="template">Template / Asset Pack</option>
                  <option value="courses">Video Course</option>
                  <option value="software">Software / Extension</option>
                  <option value="other">Other Digital Download</option>
                </select>
              </div>

              <div className="space-y-2">
                <label className="text-xs font-semibold text-slate-300">Price Amount *</label>
                <input
                  type="number"
                  step="0.01"
                  required
                  min="0"
                  value={priceAmount}
                  onChange={(e) => setPriceAmount(e.target.value)}
                  className="w-full bg-slate-950/60 border border-slate-800 focus:border-indigo-500 text-slate-200 px-4 py-2.5 rounded-xl text-sm outline-none transition-colors"
                />
              </div>

              <div className="space-y-2">
                <label className="text-xs font-semibold text-slate-300">Currency</label>
                <select
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  className="w-full bg-slate-950/60 border border-slate-800 focus:border-indigo-500 text-slate-300 px-4 py-2.5 rounded-xl text-sm outline-none transition-colors"
                >
                  <option value="THB">THB (฿)</option>
                  <option value="USD">USD ($)</option>
                  <option value="EUR">EUR (€)</option>
                </select>
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-300">Short Pitch / One-Liner Description</label>
              <input
                type="text"
                maxLength={500}
                placeholder="Provide a compelling 1-sentence description that appears beneath the title (max 500 chars)"
                value={shortDescription}
                onChange={(e) => setShortDescription(e.target.value)}
                className="w-full bg-slate-950/60 border border-slate-800 focus:border-indigo-500 text-slate-200 px-4 py-2.5 rounded-xl text-sm outline-none transition-colors"
              />
            </div>

            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-300">Cover Image URL</label>
              <input
                type="url"
                placeholder="https://example.com/assets/product-cover.jpg"
                value={coverImageUrl}
                onChange={(e) => setCoverImageUrl(e.target.value)}
                className="w-full bg-slate-950/60 border border-slate-800 focus:border-indigo-500 text-slate-200 px-4 py-2.5 rounded-xl text-sm outline-none transition-colors"
              />
            </div>

            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-300">Product Detailed Description</label>
              <textarea
                rows={4}
                placeholder="Write an internal description detailing inventory, usage, or notes."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full bg-slate-950/60 border border-slate-800 focus:border-indigo-500 text-slate-200 px-4 py-2.5 rounded-xl text-sm outline-none transition-colors resize-y"
              />
            </div>

            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-300">Sales Landing Page Content (Markdown / HTML Supported)</label>
              <textarea
                rows={10}
                placeholder="Markdown is fully compiled. Describe the benefits, outline structural breakdown, address objections, and provide social proof."
                value={salesPageContent}
                onChange={(e) => setSalesPageContent(e.target.value)}
                className="w-full bg-slate-950/60 border border-slate-800 focus:border-indigo-500 text-slate-200 px-4 py-3 rounded-xl text-sm outline-none font-mono transition-colors resize-y"
              />
            </div>

            <div className="flex justify-end gap-3 pt-4 border-t border-slate-850">
              <Link
                to="/products"
                className="px-4 py-2 bg-slate-800 hover:bg-slate-750 text-slate-300 font-medium rounded-xl text-sm transition-colors"
              >
                Cancel
              </Link>
              <button
                type="submit"
                disabled={saving}
                className="flex items-center gap-2 px-5 py-2 bg-indigo-500 hover:bg-indigo-600 disabled:opacity-50 text-white font-medium rounded-xl text-sm transition-all"
              >
                <Save size={16} />
                {saving ? "Saving..." : "Save Product Details"}
              </button>
            </div>
          </form>
        </div>

        {/* Right Panel (Assets and Meta Info) */}
        <div className="space-y-6">
          
          {/* Delivery Assets Panel */}
          <div className="bg-slate-900/40 border border-slate-800 rounded-3xl p-6 shadow-xl backdrop-blur-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-850 pb-3">
              <div>
                <h3 className="font-bold text-slate-100 text-sm flex items-center gap-2">
                  <Lock size={15} className="text-indigo-400" />
                  Delivery Assets
                </h3>
                <p className="text-[10px] text-slate-400 mt-0.5">Assets delivered automatically upon payment.</p>
              </div>
              {!isNew && (
                <button
                  onClick={() => setShowAssetModal(true)}
                  className="p-1 bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-400 rounded-lg transition-colors"
                  title="Add Delivery Asset"
                >
                  <Plus size={16} />
                </button>
              )}
            </div>

            {isNew ? (
              <div className="p-8 text-center border border-dashed border-slate-800 rounded-2xl">
                <p className="text-xs text-slate-500">Save the product first to enable delivery asset configuration.</p>
              </div>
            ) : assets.length === 0 ? (
              <div className="p-8 text-center border border-dashed border-slate-800 rounded-2xl space-y-2">
                <File className="w-8 h-8 text-slate-600 mx-auto" />
                <h4 className="text-xs font-bold text-slate-300">No delivery assets configured</h4>
                <p className="text-[10px] text-slate-500 max-w-[15rem] mx-auto">
                  A product needs at least one active delivery asset configured before it can be published.
                </p>
                <button
                  onClick={() => setShowAssetModal(true)}
                  className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold"
                >
                  Add Asset Now
                </button>
              </div>
            ) : (
              <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                {assets.map((asset) => (
                  <div 
                    key={asset.id} 
                    className={`p-3 bg-slate-950/40 border rounded-xl flex items-center justify-between gap-3 ${
                      asset.is_active ? "border-slate-850" : "border-slate-900 opacity-50"
                    }`}
                  >
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-slate-200 truncate">{asset.title}</div>
                      <div className="text-[9px] font-mono text-slate-500 uppercase tracking-wider mt-0.5">
                        Type: {asset.asset_type} • {asset.is_active ? "Active" : "Disabled"}
                      </div>
                    </div>
                    {asset.is_active && (
                      <button
                        onClick={() => handleDeactivateAsset(asset.id)}
                        className="p-1 hover:bg-rose-500/10 hover:text-rose-400 text-slate-500 rounded"
                        title="Deactivate Asset"
                      >
                        <Trash2 size={12} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Quick Sandbox Launch Checklist */}
          {!isNew && (
            <div className="bg-slate-900/40 border border-slate-800 rounded-3xl p-6 shadow-xl backdrop-blur-xl space-y-4">
              <div className="border-b border-slate-850 pb-3">
                <h3 className="font-bold text-slate-100 text-sm flex items-center gap-2">
                  <Globe size={15} className="text-indigo-400" />
                  Funnel Sandbox Launch
                </h3>
                <p className="text-[10px] text-slate-400 mt-0.5">Complete this checklist to launch public sales.</p>
              </div>

              <div className="space-y-3">
                <div className="flex items-start gap-2.5">
                  <div className="mt-0.5 text-emerald-400">
                    <Check size={14} />
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-slate-200">Product created successfully</div>
                    <div className="text-[9px] text-slate-500">Local DB entry completed.</div>
                  </div>
                </div>

                <div className="flex items-start gap-2.5">
                  <div className={assets.some(a => a.is_active) ? "mt-0.5 text-emerald-400" : "mt-0.5 text-amber-500"}>
                    {assets.some(a => a.is_active) ? <Check size={14} /> : <AlertTriangle size={14} />}
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-slate-200">Configure delivery asset</div>
                    <div className="text-[9px] text-slate-500">Provide file, course URL, or text contents.</div>
                  </div>
                </div>

                <div className="flex items-start gap-2.5">
                  <div className={status === "published" ? "mt-0.5 text-emerald-400" : "mt-0.5 text-slate-600"}>
                    {status === "published" ? <Check size={14} /> : <span className="block w-3.5 h-3.5 rounded-full border border-slate-600" />}
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-slate-200">Publish funnel</div>
                    <div className="text-[9px] text-slate-500">Bypasses draft lock to enable checkout checkouts.</div>
                  </div>
                </div>
              </div>

              {status === "published" && (
                <div className="pt-3 border-t border-slate-850">
                  <a
                    href={`/f/${user?.organization_id}/${slug}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-center gap-2 py-2 bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-400 font-semibold rounded-xl text-xs transition-colors"
                  >
                    <BookOpen size={14} />
                    View Live Sales Funnel
                  </a>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Delivery Asset Creation Modal */}
      {showAssetModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl w-full max-w-lg overflow-hidden shadow-2xl">
            <form onSubmit={handleAddAsset}>
              <div className="px-6 py-4 border-b border-slate-850 flex justify-between items-center bg-slate-950/20">
                <h3 className="font-bold text-slate-100 text-sm">Add Secure Delivery Asset</h3>
                <button
                  type="button"
                  onClick={() => setShowAssetModal(false)}
                  className="text-slate-400 hover:text-slate-250 text-sm font-medium"
                >
                  Close
                </button>
              </div>

              <div className="p-6 space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="text-xs font-semibold text-slate-300">Asset Title *</label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Master Guide PDF"
                      value={assetTitle}
                      onChange={(e) => setAssetTitle(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 focus:border-indigo-500 text-slate-200 px-3.5 py-2 rounded-xl text-xs outline-none transition-colors"
                    />
                  </div>

                  <div className="space-y-2">
                    <label className="text-xs font-semibold text-slate-300">Asset Type</label>
                    <select
                      value={assetType}
                      onChange={(e) => setAssetType(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 focus:border-indigo-500 text-slate-300 px-3.5 py-2 rounded-xl text-xs outline-none transition-colors"
                    >
                      <option value="pdf">PDF Ebook</option>
                      <option value="video">Secure Video Stream</option>
                      <option value="zip">ZIP Source Code/Asset</option>
                      <option value="text">Exclusive Written Content</option>
                      <option value="external">External Invitation URL</option>
                    </select>
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-semibold text-slate-300">Description</label>
                  <input
                    type="text"
                    placeholder="Brief instruction explaining how to use this asset"
                    value={assetDesc}
                    onChange={(e) => setAssetDesc(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 focus:border-indigo-500 text-slate-200 px-3.5 py-2 rounded-xl text-xs outline-none transition-colors"
                  />
                </div>

                {assetType === "external" ? (
                  <div className="space-y-2">
                    <label className="text-xs font-semibold text-slate-300">External Delivery URL *</label>
                    <input
                      type="url"
                      required
                      placeholder="https://exclusive-notion-template-url.com"
                      value={assetUrl}
                      onChange={(e) => setAssetUrl(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 focus:border-indigo-500 text-slate-200 px-3.5 py-2 rounded-xl text-xs outline-none transition-colors"
                    />
                  </div>
                ) : assetType === "text" ? (
                  <div className="space-y-2">
                    <label className="text-xs font-semibold text-slate-300">Exclusive Content Body *</label>
                    <textarea
                      rows={5}
                      required
                      placeholder="Input the secret content, license key, or download instructions directly..."
                      value={assetBody}
                      onChange={(e) => setAssetBody(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 focus:border-indigo-500 text-slate-200 px-3.5 py-2.5 rounded-xl text-xs outline-none font-mono resize-y"
                    />
                  </div>
                ) : (
                  <div className="space-y-2">
                    <label className="text-xs font-semibold text-slate-300">Secure Storage Path (Local file or Cloud Key) *</label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. /secure-vault/guides/ultimate-efficiency-2026.pdf"
                      value={assetStorage}
                      onChange={(e) => setAssetStorage(e.target.value)}
                      className="w-full bg-slate-950 border border-slate-800 focus:border-indigo-500 text-slate-200 px-3.5 py-2 rounded-xl text-xs outline-none transition-colors"
                    />
                  </div>
                )}
              </div>

              <div className="px-6 py-4 bg-slate-950/20 border-t border-slate-850 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setShowAssetModal(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-750 text-slate-300 font-medium rounded-xl text-xs transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-indigo-500 hover:bg-indigo-600 text-white font-medium rounded-xl text-xs transition-all"
                >
                  Add Secure Asset
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
