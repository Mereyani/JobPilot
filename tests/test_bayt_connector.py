from jobpilot.connectors.bayt import BaytConnector

SAMPLE_HTML = """
<ul class="row is-m p0 m0">
<li data-js-job="" class="col is-12 p0" data-job-id="5483555">
  <div class="row is-m no-wrap v-align-center">
    <div class="u-flex t-small u-stretch p10l">
      <div class="u-stretch">
        <h2 class="t-large-d t-small m0t m5b t-break">
          <a data-js-aid="jobID" href="/en/saudi-arabia/jobs/software-engineer-5483555/"
             title="Software Engineer">Software Engineer</a>
        </h2>
        <div class="job-company-location-wrapper"><div>Acme Corp</div></div>
      </div>
    </div>
  </div>
  <div class="jb-descr m10t t-small t-break">
    <span class="t-ai t-bold">Summary: </span>
    Build and ship backend services.
  </div>
</li>
</ul>
"""


def test_parse_extracts_job_fields():
    connector = BaytConnector()
    jobs = connector._parse(SAMPLE_HTML, country="Saudi Arabia")

    assert len(jobs) == 1
    job = jobs[0]
    assert job.external_id == "bayt:5483555"
    assert job.title == "Software Engineer"
    assert job.company == "Acme Corp"
    assert job.country == "Saudi Arabia"
    assert job.url == "https://www.bayt.com/en/saudi-arabia/jobs/software-engineer-5483555/"
    assert job.description == "Build and ship backend services."


def test_country_slug_mapping():
    connector = BaytConnector()
    assert connector._country_slug("Saudi Arabia") == "saudi-arabia"
    assert connector._country_slug("Turkey") == "turkey"
    assert connector._country_slug("Syria") == "syria"
