import { PageCard } from '../components/layout/PageCard';
import { useRegistryPreview } from '../hooks/useRegistryPreview';
import type { Policy, Rule } from '../types';

export function PolicyPage() {
  const policies = useRegistryPreview<Policy[]>('/policies', []);
  const rules = useRegistryPreview<Rule[]>('/rules', []);
  const policyList = Array.isArray(policies.data) ? policies.data : [];
  const ruleList = Array.isArray(rules.data) ? rules.data : [];

  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <PageCard title="Policy">
        {policyList.length === 0 ? (
          <ul className="list-disc space-y-2 pl-5 text-[#8da8b5]">
            <li>Critical battery policy uses 10% as the auto-return trigger.</li>
            <li>30% remains a warning threshold only.</li>
          </ul>
        ) : (
          <div className="space-y-3">
            {policyList.map((policy) => (
              <div key={policy.policy_id} className="rounded-xl border border-white/10 bg-white/5 p-4 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <strong>{policy.policy_name || policy.name}</strong>
                  <span className={`text-xs px-2 py-1 rounded whitespace-nowrap ${
                    policy.enabled
                      ? 'bg-green-500/20 text-green-400'
                      : 'bg-red-500/20 text-red-400'
                  }`}>
                    {policy.enabled ? 'Enabled' : 'Disabled'}
                  </span>
                </div>
                <p className="text-sm text-[#8da8b5]">{policy.description}</p>
                {policy.trigger_condition && (
                  <div className="text-xs bg-white/5 p-2 rounded font-mono text-[#64748b] overflow-auto max-h-16">
                    Trigger: {JSON.stringify(policy.trigger_condition, null, 1)}
                  </div>
                )}
                {policy.action && (
                  <div className="text-xs bg-white/5 p-2 rounded font-mono text-[#64748b] overflow-auto max-h-16">
                    Action: {JSON.stringify(policy.action, null, 1)}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </PageCard>
      <PageCard title="Rules">
        {ruleList.length === 0 ? (
          <p className="text-sm text-[#8da8b5]">No automation rules configured.</p>
        ) : (
          <div className="space-y-3">
            {ruleList.map((rule) => (
              <div key={rule.rule_id} className="rounded-lg border border-white/10 bg-white/5 p-3 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <strong className="text-sm">{rule.name}</strong>
                  <span className={`text-xs px-2 py-1 rounded whitespace-nowrap ${
                    rule.enabled
                      ? 'bg-green-500/20 text-green-400'
                      : 'bg-red-500/20 text-red-400'
                  }`}>
                    {rule.enabled ? 'Enabled' : 'Disabled'}
                  </span>
                </div>
                {rule.description && (
                  <p className="text-xs text-[#8da8b5]">{rule.description}</p>
                )}
                {rule.condition && (
                  <div className="text-xs bg-white/5 p-2 rounded font-mono text-[#64748b] overflow-auto max-h-16">
                    Condition: {JSON.stringify(rule.condition, null, 1)}
                  </div>
                )}
                {rule.action && (
                  <div className="text-xs bg-white/5 p-2 rounded font-mono text-[#64748b] overflow-auto max-h-16">
                    Action: {JSON.stringify(rule.action, null, 1)}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </PageCard>
    </div>
  );
}

