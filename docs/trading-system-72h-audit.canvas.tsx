import {
  BarChart,
  Button,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Grid,
  H1,
  H2,
  Row,
  Stack,
  Stat,
  Table,
  Text,
  useCanvasAction,
  useHostTheme,
} from "cursor/canvas";

const warningDays = ["Aug 30", "Aug 31", "Sep 1", "Sep 2", "Sep 3"];
const warningCounts = [17, 16, 25, 12, 8];

export default function TradingSystemAudit() {
  const theme = useHostTheme();
  const dispatch = useCanvasAction();

  const openFile = (path: string) => dispatch({ type: "openFile", path });

  return (
    <Stack gap={20} style={{ padding: 24, background: theme.bg.editor, color: theme.text.primary }}>
      <Stack gap={6}>
        <H1>Trading system — 72-hour operational audit</H1>
        <Text tone="secondary">
          Evidence captured from persisted HDD volumes and the Alpaca paper account on 3 Sep 2026.
        </Text>
      </Stack>

      <Callout tone="danger" title="Stable process, unsuccessful trading run">
        The API stayed active for about 72 hours, but Docker is stopped now. No broker orders, fills,
        positions, learned model, knowledge scenarios, or backups were produced.
      </Callout>

      <Grid columns={4} gap={12}>
        <Stat value="72.0 h" label="Recorded API runtime" tone="success" />
        <Stat value="78" label="Market stream warnings" tone="danger" />
        <Stat value="0" label="Alpaca orders / fills" tone="danger" />
        <Stat value="7 / 7" label="Unit tests passing" tone="success" />
      </Grid>

      <Grid columns="minmax(0, 1.2fr) minmax(280px, 0.8fr)" gap={16}>
        <Stack gap={10}>
          <H2>Stream warnings by UTC date</H2>
          <BarChart
            categories={warningDays}
            series={[{ name: "Warnings", data: warningCounts, tone: "danger" }]}
            height={230}
            showValues
          />
          <Text size="small" tone="tertiary">
            17 early failures were “NoneType is not iterable”; the remaining 61 had blank timeout messages.
          </Text>
        </Stack>

        <Card>
          <CardHeader trailing="Persisted on HDD">Collected artifacts</CardHeader>
          <CardBody>
            <Stack gap={10}>
              <Row justify="space-between"><Text>Application logs</Text><Text weight="semibold">23.4 KB</Text></Row>
              <Row justify="space-between"><Text>PostgreSQL volume</Text><Text weight="semibold">70.1 MB</Text></Row>
              <Row justify="space-between"><Text>Redis snapshot</Text><Text weight="semibold">331 B</Text></Row>
              <Row justify="space-between"><Text>Knowledge scenarios</Text><Text weight="semibold">0 files</Text></Row>
              <Row justify="space-between"><Text>RL model artifacts</Text><Text weight="semibold">0 files</Text></Row>
              <Row justify="space-between"><Text>Backups</Text><Text weight="semibold">0 files</Text></Row>
            </Stack>
          </CardBody>
        </Card>
      </Grid>

      <H2>Success criteria status</H2>
      <Table
        headers={["Area", "Observed result", "Assessment"]}
        rows={[
          ["Runtime", "API log spans 72 hours; Docker engine is currently stopped", "Partial"],
          ["Market data", "Transient quote polling; no durable market dataset", "Fail"],
          ["Paper trading", "$100,000 unchanged; zero orders, fills, and positions", "Fail"],
          ["Knowledge graph", "No scenario artifacts and no recorded learning events", "Fail"],
          ["RL learning", "No model file; learning only occurs after manual feedback", "Fail"],
          ["Automated agents", "No Celery Beat schedule; worker has nothing to trigger cycles", "Fail"],
          ["Tests", "Seven isolated tests pass; no 72-hour integration assertion", "Partial"],
        ]}
        rowTone={["warning", "danger", "danger", "danger", "danger", "danger", "warning"]}
        striped
      />

      <H2>Recommended repair order</H2>
      <Table
        headers={["Priority", "Change", "Acceptance check"]}
        rows={[
          ["P0", "Block broker execution when data is synthetic, stale, or unverified", "Every order records data source and freshness"],
          ["P0", "Sync equity, buying power, positions, orders, and fills from Alpaca", "Risk checks use broker truth, not a fixed $100k portfolio"],
          ["P0", "Separate analysis from execution and add bracket orders plus a durable kill switch", "Analysis cannot place orders; stops survive restarts"],
          ["P1", "Add Celery Beat, market-calendar scheduling, idempotency, and distributed locking", "Exactly one scheduled cycle per symbol/timeframe"],
          ["P1", "Persist bars, indicators, decisions, events, and reconciliation results", "Dashboard totals match SQL and Alpaca"],
          ["P1", "Replace the process-local event bus with Redis Streams or Pub/Sub", "API and worker observe the same durable event flow"],
          ["P2", "Replace hardcoded performance and health responses with real probes", "Failure of DB, Redis, Alpaca, or Gemini degrades health"],
          ["P3", "Train RL only from reconciled closed trades; validate out of sample in shadow mode", "Promotion requires measurable benchmark improvement"],
        ]}
        rowTone={["danger", "danger", "danger", "warning", "warning", "warning", "info", "info"]}
        striped
      />

      <Card>
        <CardHeader>Relevant implementation files</CardHeader>
        <CardBody>
          <Row gap={8} wrap>
            <Button variant="secondary" onClick={() => openFile("backend/agents/data_agent.py")}>Data fallback</Button>
            <Button variant="secondary" onClick={() => openFile("backend/services/orchestrator.py")}>Execution flow</Button>
            <Button variant="secondary" onClick={() => openFile("backend/tasks/celery.py")}>Worker task</Button>
            <Button variant="secondary" onClick={() => openFile("backend/api/main.py")}>Health and metrics</Button>
          </Row>
        </CardBody>
      </Card>

      <Text size="small" tone="tertiary">
        Do not enable unattended paper auto-trading yet. A longer wait will not create durable learning data until scheduling,
        persistence, broker reconciliation, and safety gates are implemented.
      </Text>
    </Stack>
  );
}
