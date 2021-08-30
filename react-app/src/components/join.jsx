import Phase from './phase'

function Join() {
  return (
    <Phase title="Welkom">
      <div className="block">
        <p className="label has-text-weight-normal">
          Welkom op het/de (fuck lidwoorden) GAME NAAM!
          Je bent net op tijd, we gaan zo beginnen.
          Het vuur staat al aan dus kom er lekker bij zitten.
        </p>
        <form id="join-form">
          <div className="field has-addons">
            <div className="control">
              <input className="input" type="text" name="name" size="30" placeholder="Naam" />
            </div>
            <div className="control">
              <button type="submit" className="button is-primary">
                Schuif aan
              </button>
            </div>
          </div>
        </form>
      </div>
      <div className="block">
        <p className="label has-text-weight-normal">Deel de volgende link om andere mensen uit te nodigen:</p>
        <form id="game-link">
          <div className="field has-addons">
            <div className="control">
              <input className="input" type="text" name="link" size="30" value="{{ request.url }}" readonly />
            </div>
            <div className="control">
              <button type="submit" className="button">
                Kopieer
              </button>
            </div>
          </div>
        </form>
      </div>
    </Phase>
  );
}

export default Join;
