import type { TyreState } from '../replay';

export function TyreStint({ tyres }: { tyres?: TyreState | null }) {
  const compound = tyres?.compound;
  const label = compound
    ? compound.charAt(0) + compound.slice(1).toLowerCase().replaceAll('_', ' ')
    : 'Unknown';
  return (
    <section
      className="tyre-stint"
      aria-label="Tyres and stint"
      data-observed-at={tyres?.observed_at_utc ?? ''}
    >
      <div className="tyre-heading">
        <h3>Tyres &amp; stint</h3>
        {tyres?.in_pit && (
          <span className="pit-status" data-testid="pit-status">
            In pit lane
          </span>
        )}
      </div>
      <div className="tyre-compound" data-compound={compound ?? 'UNKNOWN'}>
        <span className="compound-mark" aria-hidden="true">
          {compound?.charAt(0) ?? '?'}
        </span>
        <div>
          <strong data-testid="tyre-compound">{label}</strong>
          <small>
            {tyres?.fresh == null
              ? 'Set history unknown'
              : tyres.fresh
                ? 'Started fresh'
                : 'Used set'}
          </small>
        </div>
      </div>
      <dl className="tyre-details">
        <div>
          <dt>TYRE AGE</dt>
          <dd>
            <strong data-testid="tyre-age">{tyres?.age_laps ?? '\u2014'}</strong>
            <small>completed laps</small>
          </dd>
        </div>
        <div>
          <dt>STINT</dt>
          <dd data-testid="tyre-stint">{tyres?.stint ?? '\u2014'}</dd>
        </div>
        <div>
          <dt>PIT VISITS</dt>
          <dd data-testid="pit-visits">{tyres?.pit_visits ?? '\u2014'}</dd>
        </div>
      </dl>
    </section>
  );
}
