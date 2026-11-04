// What a page shows before its first successful fetch: the title, then a spinner or the error.
import { Spinner } from "@workspace/pds/components/ui/spinner";
import Feedback from "./Feedback";
import PageStack from "./PageStack";

export default function PageLoading({ title, error }: { title: string; error: string | null }) {
  return (
    <PageStack>
      <h1 className="text-xl font-semibold">{title}</h1>
      {error ? <Feedback error={error} /> : <Spinner />}
    </PageStack>
  );
}
