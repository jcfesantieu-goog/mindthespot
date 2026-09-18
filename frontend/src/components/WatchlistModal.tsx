import React, { useState } from "react";
import { X, Star, Plus, MapPin, Trash2, ShieldCheck, CheckCircle2, AlertCircle } from "lucide-react";
import { WatchlistEntry } from "../types";
import { addWatchlistTarget } from "../lib/api";
import { cn } from "../lib/utils";

interface WatchlistModalProps {
  isOpen: boolean;
  onClose: () => void;
  watchlist: WatchlistEntry[];
  onRefreshData?: () => void;
  onRemoveTarget?: (entry: WatchlistEntry) => void;
  initialAddMode?: boolean;
}

export const WatchlistModal: React.FC<WatchlistModalProps> = ({
  isOpen,
  onClose,
  watchlist,
  onRefreshData,
  onRemoveTarget,
  initialAddMode = false,
}) => {
  const [activeTab, setActiveTab] = useState<"list" | "create">(
    initialAddMode ? "create" : "list"
  );

  // Form State
  const [name, setName] = useState("");
  const [region, setRegion] = useState("europe-west4");
  const [zones, setZones] = useState("europe-west4-a, europe-west4-b");
  const [machineTypes, setMachineTypes] = useState("c4d-standard-16, c4d-standard-32");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setStatusMsg(null);

    try {
      const zList = zones
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const mList = machineTypes
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);

      if (mList.length === 0) {
        throw new Error("At least one machine type is required.");
      }

      await addWatchlistTarget({
        name: name.trim() || `${region} Workload`,
        region: region.trim(),
        zones: zList,
        machine_types: mList,
      });

      setStatusMsg({
        type: "success",
        text: `Watchlist "${name.trim() || region}" registered successfully!`,
      });
      setName("");
      onRefreshData?.();
      setTimeout(() => {
        setActiveTab("list");
        setStatusMsg(null);
      }, 1200);
    } catch (err: any) {
      setStatusMsg({
        type: "error",
        text: err.message || "Failed to create watchlist target.",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-150">
      <div
        className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl flex flex-col max-h-[85vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20">
              <Star className="w-5 h-5 fill-amber-400" />
            </div>
            <div>
              <h2 className="text-sm font-bold font-mono text-slate-100">
                Watchlist Fleet Management
              </h2>
              <p className="text-xs text-slate-400 font-mono">
                Configure and monitor multiple dedicated workload targets
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Controls */}
        <div className="flex items-center justify-between px-6 pt-3 pb-2 border-b border-slate-800/80 bg-slate-950/30">
          <div className="flex items-center gap-2 font-mono text-xs">
            <button
              onClick={() => {
                setActiveTab("list");
                setStatusMsg(null);
              }}
              className={cn(
                "px-3 py-1.5 rounded-lg transition-all font-semibold",
                activeTab === "list"
                  ? "bg-slate-800 text-slate-100 border border-slate-700"
                  : "text-slate-400 hover:text-slate-200"
              )}
            >
              Configured Watchlists ({watchlist.length})
            </button>
            <button
              onClick={() => {
                setActiveTab("create");
                setStatusMsg(null);
              }}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all font-semibold",
                activeTab === "create"
                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                  : "text-slate-400 hover:text-slate-200"
              )}
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add New Watchlist</span>
            </button>
          </div>
        </div>

        {/* Status Message */}
        {statusMsg && (
          <div
            className={cn(
              "mx-6 mt-3 p-3 rounded-xl border text-xs font-mono flex items-center gap-2",
              statusMsg.type === "success"
                ? "bg-emerald-950/50 border-emerald-800/40 text-emerald-300"
                : "bg-rose-950/50 border-rose-800/40 text-rose-300"
            )}
          >
            {statusMsg.type === "success" ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            ) : (
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
            )}
            <span>{statusMsg.text}</span>
          </div>
        )}

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {activeTab === "list" && (
            <>
              {watchlist.length === 0 ? (
                <div className="text-center py-12 text-slate-500 font-mono text-xs space-y-2">
                  <Star className="w-8 h-8 mx-auto text-slate-600" />
                  <p className="text-slate-300 font-bold">No Watchlists Configured</p>
                  <p className="max-w-xs mx-auto text-slate-400">
                    Create dedicated watchlists to monitor high-priority workloads across zones and machine types.
                  </p>
                  <button
                    onClick={() => setActiveTab("create")}
                    className="mt-2 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold transition-colors"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Create Your First Watchlist</span>
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  {watchlist.map((entry, idx) => (
                    <div
                      key={`${entry.region}-${entry.name || idx}`}
                      className="bg-slate-950 border border-slate-800/80 rounded-xl p-4 flex flex-col justify-between hover:border-slate-700 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="flex items-center gap-2">
                            <Star className="w-4 h-4 text-amber-400 fill-amber-400 shrink-0" />
                            <h3 className="font-mono font-bold text-xs text-slate-100">
                              {entry.name || `${entry.region} Workload`}
                            </h3>
                            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                              {entry.region}
                            </span>
                          </div>

                          <div className="mt-2 space-y-1.5 font-mono text-xs text-slate-400">
                            <div className="flex items-center gap-1.5">
                              <MapPin className="w-3 h-3 text-slate-500" />
                              <span>Zones:</span>
                              <span className="text-slate-200">
                                {entry.zones.length > 0 ? entry.zones.join(", ") : "All regional zones"}
                              </span>
                            </div>

                            <div className="flex flex-wrap gap-1 pt-1">
                              {entry.machine_types.map((mt) => (
                                <span
                                  key={mt}
                                  className="px-2 py-0.5 rounded bg-slate-900 text-cyan-300 border border-slate-800 text-[11px]"
                                >
                                  {mt}
                                </span>
                              ))}
                            </div>
                          </div>
                        </div>

                        {onRemoveTarget && (
                          <button
                            onClick={() => onRemoveTarget(entry)}
                            className="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-950/20 transition-colors"
                            title="Remove Watchlist Target"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </div>

                      <div className="mt-3 pt-2.5 border-t border-slate-800/60 flex items-center justify-between text-[11px] font-mono text-slate-500">
                        <span className="flex items-center gap-1 text-emerald-400">
                          <ShieldCheck className="w-3.5 h-3.5" />
                          Monitored
                        </span>
                        <span>
                          {entry.alert_threshold_z ? `Z ≥ ${entry.alert_threshold_z}` : "Default Z ≥ 2.5"}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {activeTab === "create" && (
            <form onSubmit={handleSubmit} className="space-y-4 font-mono text-xs">
              <div className="space-y-1">
                <label className="block text-slate-300 font-bold">Workload / Team Label</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Data Engineering Batch or ML Inference Fleet"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-100 placeholder-slate-600 focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="block text-slate-300 font-bold">GCP Region *</label>
                  <input
                    type="text"
                    value={region}
                    onChange={(e) => setRegion(e.target.value)}
                    placeholder="e.g. europe-west4, us-central1"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-100 focus:outline-none focus:border-cyan-500"
                    required
                  />
                </div>

                <div className="space-y-1">
                  <label className="block text-slate-300 font-bold">Zones (comma separated) *</label>
                  <input
                    type="text"
                    value={zones}
                    onChange={(e) => setZones(e.target.value)}
                    placeholder="e.g. europe-west4-a, europe-west4-b"
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-100 focus:outline-none focus:border-cyan-500"
                    required
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label className="block text-slate-300 font-bold">Machine Types (comma separated) *</label>
                <input
                  type="text"
                  value={machineTypes}
                  onChange={(e) => setMachineTypes(e.target.value)}
                  placeholder="e.g. c4d-standard-16, c3d-standard-16, c4a-standard-16"
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-100 focus:outline-none focus:border-cyan-500"
                  required
                />
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setActiveTab("list")}
                  className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold transition-colors disabled:opacity-50"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>{isSubmitting ? "Registering..." : "Save Watchlist Target"}</span>
                </button>
              </div>
            </form>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-800 bg-slate-950/40 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-mono text-slate-200 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
