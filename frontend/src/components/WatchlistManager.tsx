import React, { useState } from "react";
import { Plus, Star, ShieldCheck, MapPin, Trash2 } from "lucide-react";
import { WatchlistEntry } from "../types";
import { addWatchlistTarget } from "../lib/api";

interface WatchlistManagerProps {
  watchlist: WatchlistEntry[];
  onRefresh: () => void;
  onRemoveTarget?: (entry: WatchlistEntry) => void;
}

export const WatchlistManager: React.FC<WatchlistManagerProps> = ({
  watchlist,
  onRefresh,
  onRemoveTarget,
}) => {
  const [isAdding, setIsAdding] = useState(false);
  const [name, setName] = useState("");
  const [region, setRegion] = useState("europe-west4");
  const [zones, setZones] = useState("europe-west4-a, europe-west4-b");
  const [machineTypes, setMachineTypes] = useState("c4d-standard-16, c3d-standard-16, c4a-standard-16");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

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

      await addWatchlistTarget({
        name: name || "Custom Team Target",
        region,
        zones: zList,
        machine_types: mList,
      });

      setStatusMsg("Successfully added custom targets to watchlist!");
      setIsAdding(false);
      setName("");
      onRefresh();
    } catch (err: any) {
      setStatusMsg(`Error adding targets: ${err.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 flex items-center justify-between flex-wrap gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Star className="w-5 h-5 text-amber-400 fill-amber-400" />
            <h2 className="text-lg font-bold font-mono text-slate-100">
              Custom Workload Watchlist
            </h2>
          </div>
          <p className="text-xs text-slate-400 max-w-xl">
            Prioritize dedicated instances and business-critical workloads. Watchlist targets receive
            heightened alerting priority in the Situation Room.
          </p>
        </div>

        <button
          onClick={() => setIsAdding(!isAdding)}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs transition-colors shadow-sm font-mono"
        >
          <Plus className="w-4 h-4" />
          <span>{isAdding ? "Cancel" : "Add Custom Watchlist Pool"}</span>
        </button>
      </div>

      {statusMsg && (
        <div className="p-3 rounded-lg bg-emerald-950/60 border border-emerald-800/40 text-emerald-300 text-xs font-mono">
          {statusMsg}
        </div>
      )}

      {/* Add Custom Target Form */}
      {isAdding && (
        <form
          onSubmit={handleSubmit}
          className="bg-slate-950/80 border border-slate-800 rounded-xl p-5 space-y-4 font-mono text-xs"
        >
          <h3 className="text-sm font-bold text-slate-200">
            Register Custom Watchlist Workload
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-slate-400 mb-1">Workload / Team Label</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. ML Inference Fleet or Batch Analytics"
                className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-cyan-500"
              />
            </div>

            <div>
              <label className="block text-slate-400 mb-1">GCP Region</label>
              <input
                type="text"
                value={region}
                onChange={(e) => setRegion(e.target.value)}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-cyan-500"
                required
              />
            </div>

            <div>
              <label className="block text-slate-400 mb-1">Zones (comma separated)</label>
              <input
                type="text"
                value={zones}
                onChange={(e) => setZones(e.target.value)}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-cyan-500"
                required
              />
            </div>

            <div>
              <label className="block text-slate-400 mb-1">Machine Types (comma separated)</label>
              <input
                type="text"
                value={machineTypes}
                onChange={(e) => setMachineTypes(e.target.value)}
                className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-cyan-500"
                required
              />
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setIsAdding(false)}
              className="px-4 py-2 rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-bold"
            >
              {isSubmitting ? "Adding..." : "Save Watchlist Target"}
            </button>
          </div>
        </form>
      )}

      {/* Watchlist Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {watchlist.map((entry, idx) => (
          <div
            key={`${entry.region}-${idx}`}
            className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col justify-between"
          >
            <div>
              <div className="flex items-start justify-between gap-2 mb-2">
                <span className="font-mono font-bold text-sm text-slate-100 flex items-center gap-1.5">
                  <Star className="w-3.5 h-3.5 text-amber-400 fill-amber-400" />
                  {entry.name || "Default Workload"}
                </span>
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                    {entry.region}
                  </span>
                  {onRemoveTarget && (
                    <button
                      onClick={() => onRemoveTarget(entry)}
                      className="p-1 rounded text-slate-500 hover:text-red-400 hover:bg-slate-800 transition-colors"
                      title="Remove from Watchlist"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>

              <div className="space-y-2 mt-3 font-mono text-xs">
                <div className="flex items-center gap-1 text-slate-400">
                  <MapPin className="w-3.5 h-3.5 text-slate-500" />
                  <span>Zones:</span>
                  <span className="text-slate-200">
                    {entry.zones.length > 0 ? entry.zones.join(", ") : "All regional zones"}
                  </span>
                </div>

                <div className="flex flex-wrap gap-1 mt-2">
                  {entry.machine_types.map((mt) => (
                    <span
                      key={mt}
                      className="px-2 py-0.5 rounded bg-slate-950 text-cyan-300 border border-slate-800 text-[11px]"
                    >
                      {mt}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-[11px] font-mono text-slate-500">
              <span className="flex items-center gap-1">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                Active Monitoring
              </span>
              <span>
                {entry.alert_threshold_z ? `Z ≥ ${entry.alert_threshold_z}` : "Default Z ≥ 2.5"}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
