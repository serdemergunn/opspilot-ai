using System.Data.Common;
using OpsPilot.Api.Data;

namespace OpsPilot.Api.Tests.Unit;

public class DatabaseUnavailableHandlerTests
{
    private sealed class FakeDbException(string message) : DbException(message);

    [Fact]
    public void Recognizes_database_failures_directly_and_when_wrapped()
    {
        Assert.True(DatabaseUnavailableHandler.IsDatabaseFailure(new FakeDbException("connection refused")));
        Assert.True(DatabaseUnavailableHandler.IsDatabaseFailure(
            new InvalidOperationException("transient failure", new FakeDbException("connection refused"))));
        Assert.True(DatabaseUnavailableHandler.IsDatabaseFailure(new TimeoutException()));
    }

    [Fact]
    public void Leaves_other_errors_to_the_default_handler() =>
        Assert.False(DatabaseUnavailableHandler.IsDatabaseFailure(new InvalidOperationException("a bug")));
}
